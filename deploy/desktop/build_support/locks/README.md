Commit three hash-locked dependency files here before tagging:

- `macos-arm64.txt`
- `macos-x86_64.txt`
- `windows-x64.txt`

Resolve each on the matching native operating system and Python 3.12.15. Include the application's runtime dependencies, all build-backend dependencies, PyInstaller 6.22.3, and all transitive dependencies. Generate hashes and exact versions. The root README gives the lock-generation command. No dependency versions are fabricated in this draft.
