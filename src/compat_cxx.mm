// C++ exception diagnostics. An exception that reaches a noexcept frame ends in
// __clang_call_terminate -> std::terminate after the stack is already unwound, so the
// crash report shows neither the exception nor where it was thrown.
//
//  * ___cxa_throw: patch.py retargets the main binary's import here (HOOKS). Records the
//    type + backtrace of each thread's last throw, then calls the real one.
//  * terminate handler: logs type, what() / NSException reason, the last throw's
//    backtrace and the terminate-site stack, then chains to the previous handler.
//  * std::set_terminate: also retargeted; a handler installed later by the app becomes
//    our "previous" instead of replacing us.
// Frames print as image+offset; main-binary addresses = 0x100000000 + offset.
// Only built with VOIPSHIM_LOG: without it the shim exports no hooks and patch.py leaves
// those imports alone.

#if VOIPSHIM_LOG

#import <Foundation/Foundation.h>
#include <atomic>
#include <cxxabi.h>
#include <dlfcn.h>
#include <exception>
#include <execinfo.h>
#include <string.h>
#include <typeinfo>

extern "C" void voipshim_log(NSString *msg);

namespace {

constexpr int kMaxFrames = 48;
struct LastThrow {
    void *pcs[kMaxFrames];
    int n;
    const std::type_info *type;
};
thread_local LastThrow lastThrow;

using ThrowFn = void (*)(void *, std::type_info *, void (*)(void *));
using SetTermFn = std::terminate_handler (*)(std::terminate_handler);
ThrowFn realThrow;
SetTermFn realSetTerminate;
std::terminate_handler prevTerminate;

void *abiSym(const char *name) {
    static void *h = dlopen("/usr/lib/libc++abi.dylib", RTLD_NOLOAD | RTLD_LAZY);
    return dlsym(h, name);
}

NSString *demangle(const char *mangled) {
    int st = 0;
    char *d = abi::__cxa_demangle(mangled, nullptr, nullptr, &st);
    NSString *s = @(d && !st ? d : mangled);
    free(d);
    return s;
}

NSString *frames(void *const *pcs, int n) {
    NSMutableString *s = [NSMutableString string];
    for (int i = 0; i < n; i++) {
        Dl_info di;
        if (dladdr(pcs[i], &di) && di.dli_fbase) {
            const char *img = strrchr(di.dli_fname, '/');
            [s appendFormat:@"\n%2d %s+0x%lx %s", i, img ? img + 1 : di.dli_fname,
                            (unsigned long)((uintptr_t)pcs[i] - (uintptr_t)di.dli_fbase),
                            di.dli_sname ?: ""];
        } else {
            [s appendFormat:@"\n%2d %p", i, pcs[i]];
        }
    }
    return s;
}

void onTerminate() {
    static std::atomic<bool> entered;
    if (entered.exchange(true))   // app handler saved via get_terminate() and chains back
        abort();
    NSString *what = @"";
    const std::type_info *t = abi::__cxa_current_exception_type();
    if (t) {
        try {
            throw;
        } catch (NSException *e) {
            what = [NSString stringWithFormat:@"NSException %@: %@", e.name, e.reason];
        } catch (const std::exception &e) {
            what = @(e.what());
        } catch (...) {
        }
    }
    void *pcs[kMaxFrames];
    int n = backtrace(pcs, kMaxFrames);
    NSString *thrown = lastThrow.n && lastThrow.type == t
        ? frames(lastThrow.pcs, lastThrow.n) : @" (no recorded throw of this type on this thread)";
    voipshim_log([NSString stringWithFormat:@"TERMINATE %@: %@\n-- thrown at:%@\n-- terminate at:%@",
                  t ? demangle(t->name()) : @"(no current exception)", what, thrown, frames(pcs, n)]);
    if (prevTerminate)
        prevTerminate();
    abort();
}

}  // namespace

extern "C" __attribute__((visibility("default"), noreturn))
void voipshim_cxa_throw(void *obj, std::type_info *type, void (*dtor)(void *)) __asm__("___cxa_throw");
extern "C" void voipshim_cxa_throw(void *obj, std::type_info *type, void (*dtor)(void *)) {
    lastThrow.n = backtrace(lastThrow.pcs, kMaxFrames);
    lastThrow.type = type;
    realThrow(obj, type, dtor);
    __builtin_unreachable();
}

extern "C" __attribute__((visibility("default")))
std::terminate_handler voipshim_set_terminate(std::terminate_handler h) noexcept __asm__("__ZSt13set_terminatePFvvE");
extern "C" std::terminate_handler voipshim_set_terminate(std::terminate_handler h) noexcept {
    std::terminate_handler old = prevTerminate;
    prevTerminate = h;
    return old;
}

extern "C" void voipshim_install_cxx(void) {
    realThrow = (ThrowFn)abiSym("__cxa_throw");
    realSetTerminate = (SetTermFn)abiSym("_ZSt13set_terminatePFvvE");
    prevTerminate = realSetTerminate(onTerminate);
    voipshim_log([NSString stringWithFormat:@"C++ diagnostics: __cxa_throw %p, set_terminate %p, previous handler %p",
                  realThrow, realSetTerminate, prevTerminate]);
}

#endif  // VOIPSHIM_LOG
