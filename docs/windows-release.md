# Windows release and signing

The `Build Windows desktop app` workflow builds NSIS and MSI installers, generates SHA-256
checksums, and can publish a GitHub prerelease. The workflow keeps producing unsigned preview
installers until an Authenticode certificate is configured.

## Optional Authenticode signing

Export the Windows code-signing certificate as a password-protected PFX. Add these GitHub Actions
secrets to the repository:

- `WINDOWS_CERTIFICATE`: Base64 representation of the complete PFX file.
- `WINDOWS_CERTIFICATE_PASSWORD`: Password used when exporting the PFX.

The workflow imports the certificate only into the temporary runner certificate store, signs with
SHA-256, and timestamps the result. Never commit the PFX or its password.

## Update path

The packaged application first checks the hosted GitSeek interface supplied to the Windows build
workflow. When it is reachable, the desktop window loads that interface, so search behavior, copy,
and normal UI changes become available without reinstalling the application. When the hosted site
cannot be reached within three seconds, the packaged interface remains available as an offline
fallback.

Native Tauri, permission, icon, and installer changes still require a new Windows package. The
application settings page checks the repository's latest GitHub Release and links to its download
page for those updates. Fully automatic native installation requires a separate Tauri updater
signing key and stable update manifest; the private key must remain in GitHub Secrets and an offline
backup, never in this repository.

## Release checklist

1. Run all API tests and the web/desktop build.
2. Run the Windows workflow with the public API URL and the intended semantic version.
3. Install the NSIS package on a clean Windows account.
4. Verify the publisher signature when a certificate is configured.
5. Verify `/health`, one broad search, one constrained search, project details, save, and feedback.
6. Publish the workflow artifact as a prerelease before promoting it to a stable release.
