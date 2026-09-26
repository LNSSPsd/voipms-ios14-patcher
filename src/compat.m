// Fallbacks for iOS 15/16 ObjC methods the app calls unguarded (built with min iOS 16,
// so the compiler dropped every @available check). Each is added only if the class
// doesn't already respond — on a system that has the real method this is a no-op.
// Found by intersecting the app's __objc_selrefs with ios(15|16)-annotated
// declarations in the iOS 16.5 SDK (see ../NOTES.md).

#import <Foundation/Foundation.h>
#import <objc/runtime.h>
#import <objc/message.h>

#if VOIPSHIM_LOG
// Diagnostics -> <app>/Documents/voipshim.log (app has UIFileSharingEnabled, so it's
// reachable from Files / Finder). iOS 14 crash reports omit ObjC exception reasons.
// Build with VOIPSHIM_LOG=1 (src/build-shim.sh); off by default.
static NSFileHandle *logFH;

static void shimlog(NSString *fmt, ...) NS_FORMAT_FUNCTION(1, 2);
static void shimlog(NSString *fmt, ...) {
    va_list ap;
    va_start(ap, fmt);
    NSString *msg = [[NSString alloc] initWithFormat:fmt arguments:ap];
    va_end(ap);
    NSLog(@"voipshim: %@", msg);
    @synchronized([NSFileHandle class]) {
        if (!logFH) return;
        NSString *line = [NSString stringWithFormat:@"%@ %@\n", [NSDate date], msg];
        @try { [logFH writeData:[line dataUsingEncoding:NSUTF8StringEncoding]]; } @catch (id e) {}
    }
}

static void openLog(void) {
    NSString *docs = [NSHomeDirectory() stringByAppendingPathComponent:@"Documents"];
    NSString *path = [docs stringByAppendingPathComponent:@"voipshim.log"];
    NSFileManager *fm = [NSFileManager defaultManager];
    [fm createDirectoryAtPath:docs withIntermediateDirectories:YES attributes:nil error:nil];
    NSDictionary *a = [fm attributesOfItemAtPath:path error:nil];
    if (!a || [a fileSize] > 512 * 1024)
        [fm createFileAtPath:path contents:nil attributes:nil];
    logFH = [NSFileHandle fileHandleForWritingAtPath:path];
    [logFH seekToEndOfFile];
    shimlog(@"=== launch pid %d, %@", getpid(), [[NSProcessInfo processInfo] operatingSystemVersionString]);
}

static void logUnrecognized(id obj, SEL sel, BOOL meta) {
    shimlog(@"UNRECOGNIZED %c[%s %s]\n%@", meta ? '+' : '-', object_getClassName(obj),
            sel_getName(sel), [[NSThread callStackSymbols] componentsJoinedByString:@"\n"]);
}

static NSUncaughtExceptionHandler *prevHandler;
static void onUncaught(NSException *e) {
    shimlog(@"UNCAUGHT %@: %@\n%@", e.name, e.reason, [e.callStackSymbols componentsJoinedByString:@"\n"]);
    if (prevHandler) prevHandler(e);
}

__attribute__((visibility("hidden"))) void voipshim_log(NSString *msg) { shimlog(@"%@", msg); }
void voipshim_install_cxx(void);   // compat_cxx.mm

static void installDiagnostics(void) {
    openLog();
    voipshim_install_cxx();
    for (int meta = 0; meta < 2; meta++) {
        Class c = meta ? object_getClass([NSObject class]) : [NSObject class];
        Method m = class_getInstanceMethod(c, @selector(doesNotRecognizeSelector:));
        void (*orig)(id, SEL, SEL) = (void *)method_getImplementation(m);
        method_setImplementation(m, imp_implementationWithBlock(^(id self, SEL sel) {
            logUnrecognized(self, sel, meta);
            orig(self, @selector(doesNotRecognizeSelector:), sel);
        }));
    }
    prevHandler = NSGetUncaughtExceptionHandler();
    NSSetUncaughtExceptionHandler(onUncaught);
}
#else
#define shimlog(...) ((void)0)
static void installDiagnostics(void) {}
#endif

static void add(const char *cls, BOOL meta, const char *name, const char *types, id block) {
    Class c = objc_getClass(cls);
    if (!c) return;
    if (meta) c = object_getClass(c);
    SEL s = sel_registerName(name);
    if (class_getInstanceMethod(c, s)) return;
    class_addMethod(c, s, imp_implementationWithBlock(block), types);
    shimlog(@"added %c[%s %s]", meta ? '+' : '-', cls, name);
}

// associated-object backed property (getter returns stored value or default)
static void objProp(const char *cls, const char *get, const char *set) {
    SEL key = sel_registerName(get);
    add(cls, NO, get, "@@:", ^id(id self) { return objc_getAssociatedObject(self, key); });
    add(cls, NO, set, "v@:@", ^(id self, id v) {
        objc_setAssociatedObject(self, key, v, OBJC_ASSOCIATION_RETAIN_NONATOMIC);
    });
}

static void intProp(const char *cls, const char *get, const char *set) {
    SEL key = sel_registerName(get);
    add(cls, NO, get, "q@:", ^NSInteger(id self) {
        return [objc_getAssociatedObject(self, key) integerValue];
    });
    add(cls, NO, set, "v@:q", ^(id self, NSInteger v) {
        objc_setAssociatedObject(self, key, @(v), OBJC_ASSOCIATION_RETAIN_NONATOMIC);
    });
}

static void boolProp(const char *cls, const char *get, const char *set) {
    SEL key = sel_registerName(get);
    add(cls, NO, get, "B@:", ^BOOL(id self) {
        return [objc_getAssociatedObject(self, key) boolValue];
    });
    add(cls, NO, set, "v@:B", ^(id self, BOOL v) {
        objc_setAssociatedObject(self, key, @(v), OBJC_ASSOCIATION_RETAIN_NONATOMIC);
    });
}

#define MSG(ret, ...) ((ret (*)(__VA_ARGS__))objc_msgSend)

// Nibs compiled for iOS 15+ archive IB "Plain/Filled" buttons as UIButton +
// UIButtonConfiguration (7 buttons in 3 nibs; title only inside the configuration).
// On 14 that class doesn't exist: register a stub that decodes the parts we can use,
// and have -[UIButton initWithCoder:] apply them the legacy way.
static NSString *const kCfgKeys[] = {
    @"UIButtonConfigurationTitle", @"UIButtonConfigurationSubtitle",
    @"UIButtonConfigurationImage", @"UIButtonConfigurationBaseForegroundColor",
};

// SIM carrier info is not exposed to the app: CTTelephonyNetworkInfo reports no carriers.
// libsoftphone derives call-handling settings from it.
static void hideCarrierInfo(void) {
    Class c = objc_getClass("CTTelephonyNetworkInfo");
    if (!c) { shimlog(@"CTTelephonyNetworkInfo not found, carrier info not hidden"); return; }
    Method m = class_getInstanceMethod(c, sel_registerName("serviceSubscriberCellularProviders"));
    if (m) method_setImplementation(m, imp_implementationWithBlock(^id(id self) { return @{}; }));
    m = class_getInstanceMethod(c, sel_registerName("subscriberCellularProvider"));
    if (m) method_setImplementation(m, imp_implementationWithBlock(^id(id self) { return nil; }));
    shimlog(@"carrier info hidden");
}

static void buttonConfigurationStub(void) {
    if (objc_getClass("UIButtonConfiguration")) return;  // real one present (iOS 15+)
    Class c = objc_allocateClassPair([NSObject class], "UIButtonConfiguration", 0);
    static char kVals;
    class_addMethod(c, @selector(initWithCoder:), imp_implementationWithBlock(^id(id self, NSCoder *coder) {
        NSMutableDictionary *vals = [NSMutableDictionary dictionary];
        for (size_t i = 0; i < sizeof kCfgKeys / sizeof *kCfgKeys; i++) {
            id v = [coder decodeObjectForKey:kCfgKeys[i]];
            if (v) vals[kCfgKeys[i]] = v;
        }
        objc_setAssociatedObject(self, &kVals, vals, OBJC_ASSOCIATION_RETAIN_NONATOMIC);
        return self;
    }), "@@:@");
    class_addMethod(c, @selector(encodeWithCoder:), imp_implementationWithBlock(^(id self, NSCoder *coder) {}), "v@:@");
    class_addMethod(c, @selector(copyWithZone:), imp_implementationWithBlock(^id(id self, void *z) { return self; }), "@@:^v");
    class_addMethod(c, sel_registerName("voipshim_values"), imp_implementationWithBlock(^id(id self) {
        return objc_getAssociatedObject(self, &kVals);
    }), "@@:");
    class_addMethod(object_getClass(c), @selector(supportsSecureCoding),
                    imp_implementationWithBlock(^BOOL(id cls) { return YES; }), "B@:");
    objc_registerClassPair(c);
    shimlog(@"registered stub UIButtonConfiguration");

    Class button = objc_getClass("UIButton");
    Method m = class_getInstanceMethod(button, @selector(initWithCoder:));
    if (!m) return;
    id (*orig)(id, SEL, NSCoder *) = (void *)method_getImplementation(m);
    method_setImplementation(m, imp_implementationWithBlock(^id(id self, NSCoder *coder) {
        self = orig(self, @selector(initWithCoder:), coder);
        if (!self || ![coder containsValueForKey:@"UIButtonConfiguration"]) return self;
        id cfg = [coder decodeObjectForKey:@"UIButtonConfiguration"];
        NSDictionary *v = [cfg respondsToSelector:sel_registerName("voipshim_values")]
            ? MSG(id, id, SEL)(cfg, sel_registerName("voipshim_values")) : nil;
        id title = v[@"UIButtonConfigurationTitle"];
        id color = v[@"UIButtonConfigurationBaseForegroundColor"];
        id image = v[@"UIButtonConfigurationImage"];
        if ([title isKindOfClass:[NSAttributedString class]] && [title length])
            MSG(void, id, SEL, id, NSUInteger)(self, sel_registerName("setAttributedTitle:forState:"), title, 0);
        else if ([title isKindOfClass:[NSString class]])
            MSG(void, id, SEL, id, NSUInteger)(self, sel_registerName("setTitle:forState:"), title, 0);
        if (image)
            MSG(void, id, SEL, id, NSUInteger)(self, sel_registerName("setImage:forState:"), image, 0);
        if (color) {
            MSG(void, id, SEL, id)(self, sel_registerName("setTintColor:"), color);
            MSG(void, id, SEL, id, NSUInteger)(self, sel_registerName("setTitleColor:forState:"), color, 0);
        }
        return self;
    }));
}

__attribute__((constructor)) static void voipshim_compat(void) {
    installDiagnostics();
    buttonConfigurationStub();
    hideCarrierInfo();

    // UIKit
    add("UIWindowScene", NO, "keyWindow", "@@:", ^id(id self) {
        NSArray *ws = MSG(id, id, SEL)(self, sel_registerName("windows"));
        for (id w in ws)
            if (MSG(BOOL, id, SEL)(w, sel_registerName("isKeyWindow"))) return w;
        return ws.firstObject;
    });
    add("UIColor", YES, "tintColor", "@@:", ^id(id cls) {
        return MSG(id, id, SEL)(cls, sel_registerName("systemBlueColor"));
    });
    boolProp("UIBarButtonItem", "isHidden", "setHidden:");
    boolProp("UIBarButtonItem", "isSelected", "setSelected:");
    boolProp("UIBarButtonItemGroup", "isHidden", "setHidden:");
    add("UIButton", NO, "configuration", "@@:", ^id(id self) { return nil; });
    add("UIButton", NO, "setConfiguration:", "v@:@", ^(id self, id c) {});
    add("UIButton", NO, "subtitleLabel", "@@:", ^id(id self) { return nil; });
    objProp("UIBackgroundConfiguration", "image", "setImage:");
    intProp("UIBackgroundConfiguration", "imageContentMode", "setImageContentMode:");
    boolProp("UIViewConfigurationState", "isPinned", "setPinned:");
    intProp("UIPageControl", "direction", "setDirection:");
    intProp("UINavigationItem", "style", "setStyle:");
    // iOS 15 on UIToolbar/UITabBar/UITabBarItem (UINavigationBar has had it since 13, so name-based scans
    // miss it). 14 has no scroll-edge state: standardAppearance always applies; keep value only.
    objProp("UIToolbar", "scrollEdgeAppearance", "setScrollEdgeAppearance:");
    objProp("UITabBar", "scrollEdgeAppearance", "setScrollEdgeAppearance:");
    objProp("UITabBarItem", "scrollEdgeAppearance", "setScrollEdgeAppearance:");
    objProp("UIMenuElement", "subtitle", "setSubtitle:");
    objProp("UIScene", "subtitle", "setSubtitle:");
    add("UISearchBar", NO, "isEnabled", "B@:", ^BOOL(id self) {
        return MSG(BOOL, id, SEL)(self, sel_registerName("isUserInteractionEnabled"));
    });
    add("UISearchBar", NO, "setEnabled:", "v@:B", ^(id self, BOOL e) {
        MSG(void, id, SEL, BOOL)(self, sel_registerName("setUserInteractionEnabled:"), e);
    });
    add("NSDiffableDataSourceSnapshot", NO, "reconfigureItemsWithIdentifiers:", "v@:@", ^(id self, id ids) {
        MSG(void, id, SEL, id)(self, sel_registerName("reloadItemsWithIdentifiers:"), ids);
    });

    // Foundation
    objProp("NSURLSessionTask", "delegate", "setDelegate:");
    objProp("NSPersonNameComponentsFormatter", "locale", "setLocale:");
    add("NSUUID", NO, "compare:", "q@:@", ^NSComparisonResult(NSUUID *self, NSUUID *o) {
        return [self.UUIDString compare:o.UUIDString];
    });

    // Intents: iOS 15 initializer -> iOS 12 one without suggestionType
    add("INPerson", NO,
        "initWithPersonHandle:nameComponents:displayName:image:contactIdentifier:customIdentifier:isMe:suggestionType:",
        "@@:@@@@@@Bq",
        ^id(id self, id h, id nc, id dn, id img, id cid, id cuid, BOOL me, NSInteger st) {
            return MSG(id, id, SEL, id, id, id, id, id, id, BOOL)(self,
                sel_registerName("initWithPersonHandle:nameComponents:displayName:image:contactIdentifier:customIdentifier:isMe:"),
                h, nc, dn, img, cid, cuid, me);
        });

    // UserNotifications: communication-notification decoration -> plain content
    add("UNNotificationContent", NO, "contentByUpdatingWithProvider:error:", "@@:@^@",
        ^id(id self, id provider, NSError **err) {
            if (err) *err = nil;
            return [self copy];
        });

    // CoreHaptics: AHAP file -> dictionary initializer (iOS 13)
    add("CHHapticPattern", NO, "initWithContentsOfURL:error:", "@@:@^@",
        ^id(id self, NSURL *url, NSError **err) {
            NSData *d = [NSData dataWithContentsOfURL:url options:0 error:err];
            id dict = d ? [NSJSONSerialization JSONObjectWithData:d options:0 error:err] : nil;
            if (!dict) return nil;
            return MSG(id, id, SEL, id, NSError **)(self, sel_registerName("initWithDictionary:error:"), dict, err);
        });

    // StoreKit (iOS 16.1 ad attribution): report success, do nothing
    add("SKAdNetwork", YES, "updatePostbackConversionValue:coarseValue:lockWindow:completionHandler:", "v@:q@B@?",
        ^(id cls, NSInteger v, id coarse, BOOL lock, void (^done)(NSError *)) {
            if (done) done(nil);
        });
}

// --- data symbols the app imports from iOS 15/16 frameworks ------------------
// Bound to the shim by patch.py instead of weak-null (a null data import crashes
// on first read). Values match the SDK's documented constants where known.
__attribute__((visibility("default"))) NSString *const SKANErrorDomain = @"SKANErrorDomain";
__attribute__((visibility("default"))) NSString *const SKAdNetworkCoarseConversionValueHigh = @"high";
__attribute__((visibility("default"))) NSString *const SKAdNetworkCoarseConversionValueMedium = @"medium";
__attribute__((visibility("default"))) NSString *const SKAdNetworkCoarseConversionValueLow = @"low";
// iOS 16 "default apps" settings page; the app's own settings page is the closest on 14
__attribute__((visibility("default"))) NSString *const UIApplicationOpenDefaultApplicationsSettingsURLString = @"app-settings:";

// Called by the StoreKit 2 stubs in shim.S: unreachable on 14 without a StoreKit 2
// Transaction, so reaching one is a real bug — make it loud in voipshim.log.
__attribute__((visibility("default"), noreturn)) void voipshim_missing(const char *name) {
    shimlog(@"MISSING iOS 15+ function called: %s\n%@", name,
            [[NSThread callStackSymbols] componentsJoinedByString:@"\n"]);
    abort();
}
