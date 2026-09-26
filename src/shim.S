// libvoipshim: iOS 16+ runtime entry points missing on iOS 14.3.
// Built by build-shim.sh. Semantics follow objc4-866 objc-msg-arm64.s:
// objc_{retain,release}_xN take the object in xN, then behave as objc_{retain,release}.

	.text
	.p2align 2

	.globl _objc_retain_x1
_objc_retain_x1:
	mov x0, x1
	b _objc_retain

	.globl _objc_release_x1
_objc_release_x1:
	mov x0, x1
	b _objc_release

	.globl _objc_retain_x2
_objc_retain_x2:
	mov x0, x2
	b _objc_retain

	.globl _objc_release_x2
_objc_release_x2:
	mov x0, x2
	b _objc_release

	.globl _objc_retain_x3
_objc_retain_x3:
	mov x0, x3
	b _objc_retain

	.globl _objc_release_x3
_objc_release_x3:
	mov x0, x3
	b _objc_release

	.globl _objc_retain_x4
_objc_retain_x4:
	mov x0, x4
	b _objc_retain

	.globl _objc_release_x4
_objc_release_x4:
	mov x0, x4
	b _objc_release

	.globl _objc_retain_x5
_objc_retain_x5:
	mov x0, x5
	b _objc_retain

	.globl _objc_release_x5
_objc_release_x5:
	mov x0, x5
	b _objc_release

	.globl _objc_retain_x6
_objc_retain_x6:
	mov x0, x6
	b _objc_retain

	.globl _objc_release_x6
_objc_release_x6:
	mov x0, x6
	b _objc_release

	.globl _objc_retain_x7
_objc_retain_x7:
	mov x0, x7
	b _objc_retain

	.globl _objc_release_x7
_objc_release_x7:
	mov x0, x7
	b _objc_release

	.globl _objc_retain_x8
_objc_retain_x8:
	mov x0, x8
	b _objc_retain

	.globl _objc_release_x8
_objc_release_x8:
	mov x0, x8
	b _objc_release

	.globl _objc_retain_x9
_objc_retain_x9:
	mov x0, x9
	b _objc_retain

	.globl _objc_release_x9
_objc_release_x9:
	mov x0, x9
	b _objc_release

	.globl _objc_retain_x10
_objc_retain_x10:
	mov x0, x10
	b _objc_retain

	.globl _objc_release_x10
_objc_release_x10:
	mov x0, x10
	b _objc_release

	.globl _objc_retain_x11
_objc_retain_x11:
	mov x0, x11
	b _objc_retain

	.globl _objc_release_x11
_objc_release_x11:
	mov x0, x11
	b _objc_release

	.globl _objc_retain_x12
_objc_retain_x12:
	mov x0, x12
	b _objc_retain

	.globl _objc_release_x12
_objc_release_x12:
	mov x0, x12
	b _objc_release

	.globl _objc_retain_x13
_objc_retain_x13:
	mov x0, x13
	b _objc_retain

	.globl _objc_release_x13
_objc_release_x13:
	mov x0, x13
	b _objc_release

	.globl _objc_retain_x14
_objc_retain_x14:
	mov x0, x14
	b _objc_retain

	.globl _objc_release_x14
_objc_release_x14:
	mov x0, x14
	b _objc_release

	.globl _objc_retain_x15
_objc_retain_x15:
	mov x0, x15
	b _objc_retain

	.globl _objc_release_x15
_objc_release_x15:
	mov x0, x15
	b _objc_release

	.globl _objc_retain_x19
_objc_retain_x19:
	mov x0, x19
	b _objc_retain

	.globl _objc_release_x19
_objc_release_x19:
	mov x0, x19
	b _objc_release

	.globl _objc_retain_x20
_objc_retain_x20:
	mov x0, x20
	b _objc_retain

	.globl _objc_release_x20
_objc_release_x20:
	mov x0, x20
	b _objc_release

	.globl _objc_retain_x21
_objc_retain_x21:
	mov x0, x21
	b _objc_retain

	.globl _objc_release_x21
_objc_release_x21:
	mov x0, x21
	b _objc_release

	.globl _objc_retain_x22
_objc_retain_x22:
	mov x0, x22
	b _objc_retain

	.globl _objc_release_x22
_objc_release_x22:
	mov x0, x22
	b _objc_release

	.globl _objc_retain_x23
_objc_retain_x23:
	mov x0, x23
	b _objc_retain

	.globl _objc_release_x23
_objc_release_x23:
	mov x0, x23
	b _objc_release

	.globl _objc_retain_x24
_objc_retain_x24:
	mov x0, x24
	b _objc_retain

	.globl _objc_release_x24
_objc_release_x24:
	mov x0, x24
	b _objc_release

	.globl _objc_retain_x25
_objc_retain_x25:
	mov x0, x25
	b _objc_retain

	.globl _objc_release_x25
_objc_release_x25:
	mov x0, x25
	b _objc_release

	.globl _objc_retain_x26
_objc_retain_x26:
	mov x0, x26
	b _objc_retain

	.globl _objc_release_x26
_objc_release_x26:
	mov x0, x26
	b _objc_release

	.globl _objc_retain_x27
_objc_retain_x27:
	mov x0, x27
	b _objc_retain

	.globl _objc_release_x27
_objc_release_x27:
	mov x0, x27
	b _objc_release

	.globl _objc_retain_x28
_objc_retain_x28:
	mov x0, x28
	b _objc_retain

	.globl _objc_release_x28
_objc_release_x28:
	mov x0, x28
	b _objc_release

// iOS 16 variant without the mov x29,x29 handshake; iOS 14 callee then does a real
// autorelease and this falls back to a plain retain -> same +1 result.
	.globl _objc_claimAutoreleasedReturnValue
_objc_claimAutoreleasedReturnValue:
	b _objc_retainAutoreleasedReturnValue

// sqlite 3.37+: 64-bit change count.
	.globl _sqlite3_changes64
_sqlite3_changes64:
	stp x29, x30, [sp, #-16]!
	mov x29, sp
	bl _sqlite3_changes
	sxtw x0, w0
	ldp x29, x30, [sp], #16
	ret

// Swift 5.6 runtime: false = never stack-allocate, use heap (always safe).
	.globl _swift_stdlib_isStackAllocationSafe
_swift_stdlib_isStackAllocationSafe:
	mov w0, #0
	ret

// StoreKit 2 (iOS 15): AppStore.deviceVerificationID -> Optional<UUID>.none.
// Optional<UUID> is 17 bytes, returned indirectly via x8: 16 payload bytes + tag byte 1.
	.globl "_$s8StoreKit03AppA0O20deviceVerificationID10Foundation4UUIDVSgvgZ"
"_$s8StoreKit03AppA0O20deviceVerificationID10Foundation4UUIDVSgvgZ":
	stp xzr, xzr, [x8]
	mov w9, #1
	strb w9, [x8, #16]
	ret

// StoreKit 2 Transaction getters: need a Transaction instance, which 14 can't make.
// Log + abort via voipshim_missing (compat.m) instead of jumping to null.
	.globl "_$s8StoreKit11TransactionV10originalIDs6UInt64Vvg"
"_$s8StoreKit11TransactionV10originalIDs6UInt64Vvg":
	adrp x0, Lmiss0@PAGE
	add x0, x0, Lmiss0@PAGEOFF
	b _voipshim_missing
	.globl "_$s8StoreKit11TransactionV12purchaseDate10Foundation0E0Vvg"
"_$s8StoreKit11TransactionV12purchaseDate10Foundation0E0Vvg":
	adrp x0, Lmiss1@PAGE
	add x0, x0, Lmiss1@PAGEOFF
	b _voipshim_missing
	.globl "_$s8StoreKit11TransactionV17purchasedQuantitySivg"
"_$s8StoreKit11TransactionV17purchasedQuantitySivg":
	adrp x0, Lmiss2@PAGE
	add x0, x0, Lmiss2@PAGEOFF
	b _voipshim_missing
	.globl "_$s8StoreKit11TransactionV18deviceVerification10Foundation4DataVvg"
"_$s8StoreKit11TransactionV18deviceVerification10Foundation4DataVvg":
	adrp x0, Lmiss3@PAGE
	add x0, x0, Lmiss3@PAGEOFF
	b _voipshim_missing
	.globl "_$s8StoreKit11TransactionV23deviceVerificationNonce10Foundation4UUIDVvg"
"_$s8StoreKit11TransactionV23deviceVerificationNonce10Foundation4UUIDVvg":
	adrp x0, Lmiss4@PAGE
	add x0, x0, Lmiss4@PAGEOFF
	b _voipshim_missing
	.globl "_$s8StoreKit11TransactionV2ids6UInt64Vvg"
"_$s8StoreKit11TransactionV2ids6UInt64Vvg":
	adrp x0, Lmiss5@PAGE
	add x0, x0, Lmiss5@PAGEOFF
	b _voipshim_missing
	.globl "_$s8StoreKit11TransactionV9productIDSSvg"
"_$s8StoreKit11TransactionV9productIDSSvg":
	adrp x0, Lmiss6@PAGE
	add x0, x0, Lmiss6@PAGEOFF
	b _voipshim_missing

	.section __TEXT,__cstring,cstring_literals
Lmiss0:	.asciz "$s8StoreKit11TransactionV10originalIDs6UInt64Vvg"
Lmiss1:	.asciz "$s8StoreKit11TransactionV12purchaseDate10Foundation0E0Vvg"
Lmiss2:	.asciz "$s8StoreKit11TransactionV17purchasedQuantitySivg"
Lmiss3:	.asciz "$s8StoreKit11TransactionV18deviceVerification10Foundation4DataVvg"
Lmiss4:	.asciz "$s8StoreKit11TransactionV23deviceVerificationNonce10Foundation4UUIDVvg"
Lmiss5:	.asciz "$s8StoreKit11TransactionV2ids6UInt64Vvg"
Lmiss6:	.asciz "$s8StoreKit11TransactionV9productIDSSvg"
