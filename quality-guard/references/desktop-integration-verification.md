# Desktop integration verification

Use for native Office/COM add-ins and other extensions embedded in a user's running desktop application. Finish discovery and obtain implementation scope before applying this recipe; use brainstorming's desktop-integration discovery reference for client/account compatibility.

## 1. Establish the contract and safe test boundary

- Inspect the installed type library/PIA and current official host documentation before declaring COM interfaces; a correct GUID with the wrong interface type or parameter marshalling can crash the host despite green managed tests.
- For Office `IDTExtensibility2`, verify the dual-interface contract and input `SAFEARRAY(VARIANT)` custom arguments against the installed contract. The exercised declaration uses `InterfaceIsDual` and `[In, MarshalAs(UnmanagedType.SafeArray, SafeArraySubType=VarEnum.VT_VARIANT)] ref Array custom`.
- Build a disposable native caller that exercises the actual lifecycle vtable, SAFEARRAY inputs and BSTR Ribbon result before enabling the registered add-in; ordinary managed construction does not exercise the native ABI.
- Use labelled synthetic unsent drafts and fake provider transports until the user supplies account configuration. Never read real mail, send messages, reuse another application's tokens or incur provider charges merely to prove the UI.

## 2. Verify the host surface rather than its XML alone

1. Validate static and dynamic Ribbon XML against the matching Office schema. Use callback state such as `getPressed` for dynamic toggles rather than an unsupported literal attribute.
2. Install disabled, run the isolated native gate against the registered build, and read back the exact registration and binary hash before enabling.
3. Open a labelled synthetic compose window, identify that exact window/process, click its real toolbar button, and inspect the resulting form. Check the provider menu and settings action through their real host callbacks as well.
4. Confirm both native control content and visible rendering; a non-empty text value can still render blank. Distinguish compose, pop-out reply and inline reply acceptance rather than treating one surface as proof of all three.
5. When a fixture uses Word Find, explicitly collapse its selection before testing body fallback; Find can leave the signature selected, which legitimately selects the selection-only path instead.

## 3. Preserve Word editing integrity

- Capture on the original STA, pin the callback's item/document/range, and compare COM document identity before using a selection; toolbar focus can leave Selection or its Range null, and the active selection can belong to another compose window.
- Guard the live Word text and formatting, not cached Outlook `HTMLBody`; unsaved Word formatting can change while that cached HTML remains identical.
- Diff consecutive `WordOpenXML` exports before excluding metadata from the fingerprint; measured revision IDs, drawing anchor/edit IDs and the settings normal/web view transition can change without an email-content edit. Remove only demonstrated non-content differences and retain text, formatting, links and images in the guard.
- Normalise display-only Word CR and provider LF paragraph breaks to Windows CRLF in source, context, instructions and results; a multiline native control can retain CR-only text yet render blank. Preserve the raw Word snapshot for stale-edit validation and Undo.
- Test signatures, quoted history, inline images, formatting-only changes, two active windows, closed/reopened drafts and exhausted Undo. Use grouped native Undo rather than cached HTML restoration; do not rely on `Range.InsertXML` for an inline response editor.

## 4. Recover from partial native Undo

1. Capture the complete pre-attempt text/markup and the intended original state; native `Undo(n)` can return false or throw after partially changing the document.
2. Judge the resulting state rather than the Boolean alone. Accept exact original-state restoration even when the native return reports failure.
3. If restoration is incomplete, redo **one entry at a time**, checking after each entry for exact pre-attempt text/markup, bounded by the attempted undo count; blindly redoing the batch count can overshoot into unrelated history.
4. Invalidate the review session after a history mismatch, even when recovery succeeds; do not allow further Apply/Undo using its stale ownership assumptions.
5. Test a naturally partial stack: Apply multiple times, clear native history, Apply once more, then request the session Undo. Assert that a failed restoration returns to the exact pre-attempt draft and closes off that session.

## 5. Restart and clean up without disturbing the user

- Refuse a normal restart while any inspector or inline response is open; prefer leaving an unlabelled draft untouched over assuming it belongs to the test.
- Allow normal quit, observe process exit, and preserve the existing profile. If an existing certificate warning blocks quit, decline its verified No control; never grant certificate trust or weaken Office security to make a plug-in pass.
- Try `Marshal.GetActiveObject` first. In an authorised running-host workflow, if ROT attachment is unavailable but the Outlook process still exists, the exercised fallback is `New-Object -ComObject Outlook.Application` to attach to its singleton. Keep read-only discovery probes attach-only when launching was not authorised.
- Remove only labelled, owned unsent fixtures and only the add-in's own verified resiliency records; never reset unrelated add-ins or close all inspectors. Read back connection/version after recovery and report later open-window state honestly.

## 6. Separate provider implementation from account acceptance

- Specify provider identity, authentication, exact model ID and billing independently; a consumer subscription is not evidence of API entitlement.
- Distinguish Gemini API Google OAuth from Gmail/mailbox authorisation. Check current Google documentation for project/API, consent and desktop-client requirements; do not borrow Workspace credentials.
- Keep transport fixtures, live account generation, genuine browser consent/refresh and external publisher approval as separate acceptance gates. Successful local OAuth fixtures do not certify a real project or production consent screen.
- Distinguish a complete authenticated empty model catalogue from failed/malformed/incomplete metadata. Retain its unselected connection, report zero and permit clearing obsolete reviewers; never invent a model merely to save other settings.
- Coordinate rotating OAuth refresh by literal credential-connection identity, not model/reviewer ID. Exercise the actual catalogue plus generation path with two selected and one unselected sibling: one consumed refresh token must serve both parallel generations, all matching persisted/caller credentials must agree, and a subsequent Save must not restore an old token. Test independent waiter cancellation, identity edits and disposal; do not introduce a global plaintext-token cache.
- Match persisted token-expiry CAS to the serializer's measured precision while retaining exact in-memory credential CAS. JavaScriptSerializer stores UTC milliseconds, so comparing a just-saved caller's finer ticks directly with disk can silently skip inactive-sibling reconciliation; test a submillisecond expiry and a subsequent full Save.
