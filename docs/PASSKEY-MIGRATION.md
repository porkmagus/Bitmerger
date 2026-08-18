# Passkey Migration Safety Plan

## Non-negotiable boundary

Bitwarden passkeys are complete FIDO credential objects. Desktop 1Password `.1pux` and CSV artifacts do not transport them, so Bitmerger must not claim that a desktop file import completes a passkey migration. The standards-based transfer route is direct Credential Exchange (CXP) between compatible mobile apps; without phones, the safe desktop route is deliberate per-site re-enrollment using the existing source passkey.

## Implemented controls

1. Normalize and merge Bitwarden `fido2Credentials` through the existing dedup engine.
2. Write the complete final vault to `bitmerger-merged.bitwarden.json`.
3. Write a second, Bitwarden-compatible recovery subset named `bitmerger-passkey-recovery.bitwarden.json`. It contains every final item carrying a passkey.
4. Canonicalize each full credential JSON object and calculate SHA-256 fingerprints. Store only those fingerprints, counts, and the recovery-file path in `bitmerger-merged.report.json`.
5. Re-read the recovery artifact before publication and compare its fingerprint multiset with the final merged items. Abort the transaction on a mismatch.
6. Publish the recovery file inside the same rollback transaction as the JSON, 1PUX, CSV, and report.
7. Mark passkey-bearing runs as `manual_passkey_transfer_required` and show the limitation in the GUI.

## User migration procedure

1. Run the merge and retain every generated plaintext artifact securely.
2. Import only the generated 1PUX into an empty 1Password account for desktop-portable credential data. Do not also import the CSV unless it is being used as a login-only fallback.
3. Read `passkey_migration` in the report. If its status is `manual_passkey_transfer_required`, the desktop import deliberately did not move passkeys.
4. For mobile CXP, import `bitmerger-merged.bitwarden.json` into the Bitwarden vault that will be signed in on the phone, let the mobile app sync, then initiate direct CXP into 1Password. Alternatively...[truncated]
5. Compare the report’s `credential_count` with the destination, then authenticate with each transferred passkey where practical.
6. Keep the source vault, merged Bitwarden JSON, and recovery JSON until that audit passes. Only then securely delete plaintext exports.

## Acceptance evidence

Automated tests prove that Bitmerger retains exact passkey credential objects in the recovery artifact, omits them from formats that cannot transport them, records non-reversible audit fingerprints, and rolls back all artifacts if publication fails. A real CXP acceptance test remains interactive and requires compatible installed mobile apps plus a disposable test passkey; it cannot be simulated honestly by this desktop application. The desktop re-enrollment alternative must be checked by authenticating to each relying party with the original passkey and confirming the newly saved 1Password passkey works before the original is removed.
