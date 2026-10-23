# Android test app

The APK is an Android client for the READY prototype. It displays the same mobile web UI and uses the same server-owned reviews and confirmation controls. It requires the Python backend to be running on a computer; it does not bundle Python, a model, or an API key. Payments and customer data remain synthetic.

The supported initial connection is **USB with `adb reverse`**. This keeps the existing backend bound to loopback. Installing the APK alone will show the connection instructions until the backend is reachable.

## API-ready rebuild — 23 October 2026

The signed debug APK at `android/build/outputs/AliDheaa_Topic04_READY_Debug.apk`
was rebuilt from clean commit `e0c56788daf32d153b43b2f302c7e9e8c126a8fa` using the
project-local JDK and Android SDK. SHA-256:
`11becaa358131f3029ab76cce6a1ded854b4e2fa63b0e4603a236dba44a78d06`
(33,326 bytes). The existing debug signing key was reused, so this is an
installable update to an app signed with that same key. The build verified
the manifest, DEX/ZIP integrity, 16-KiB alignment, v2/v3 signature and 38
native endpoint-policy checks.

A new loopback-only integration test exercised the same web page and HTTP
routes the APK loads: bootstrap → Iraqi-Arabic chat → local fake model API →
server-owned balance card. It also checked a simulated provider rate limit,
zero mock debits, and no credential in the app response. The full Python
suite ran 122 tests (121 passed, one optional credential-store test skipped).
This verifies the client/backend/API contract with a fake provider, **not** a
successful Gemini request or physical-device operation. `adb devices -l`
showed no connected devices; the temporary ADB daemon was stopped.

For this Windows checkout, run the backend **offline** in the foreground from
the repository directory, then follow the USB steps below. Once a separately
approved Gemini request budget exists, the backend—not the APK—can instead be
started with `scripts/ready.py serve --mode llm --provider gemini --allow-network`
and the saved Windows-user key. The previous five-request approval is treated
as exhausted because the timed-out smoke did not record its internal request
count. Do not start live mode under that old approval. The phone's connection
setting remains `http://127.0.0.1:8765/`, **never** the Gemini API URL.

## Quick start on a physical phone

Requirements: Android 8.0 or newer, a current Android System WebView, Python 3.12+, Android SDK Platform Tools (`adb`), and a USB data cable.

1. Start the backend from the repository directory on the computer:

   ```bash
   python server.py
   ```

2. Enable Developer options and USB debugging on the phone, connect the cable, and accept the phone's debugging authorization for your own computer. Check that the phone appears as `device`, not `unauthorized`:

   ```bash
   adb devices
   ```

3. In a second terminal, map the phone's local port to the computer's backend:

   ```bash
   adb reverse tcp:8765 tcp:8765
   ```

4. Install the downloaded APK, using its actual path if it is not in the current directory:

   ```bash
   adb install -r AliDheaa_Topic04_READY_Debug.apk
   ```

5. Open **READY Demo** on the phone. The native **الاتصال** button opens connection settings. Leave the default `http://127.0.0.1:8765/`. Tap **إعادة المحاولة** if you opened the app before setting up USB.

The reverse mapping may need to be recreated after the cable disconnects or the device restarts. With multiple devices, add `-s DEVICE_SERIAL` after `adb` in each command. The Android emulator can use the same reverse workflow; the server intentionally rejects emulator host aliases and LAN binds.

## Connect a live model

Configure the provider, model ID, endpoint and secret **on the Python server**, following [model setup](LLM_SETUP.md). Restart that server, then reload the APK. The Android client needs only the application's backend address. The provider's API URL is not the app's backend URL.

There is no API key input in the Android client, and no shared provider secret is built into the APK. The app's native preference store contains only the selected backend origin. A model response still cannot call the confirmation endpoint or access confirmation credentials; the server's bounded tools and ordinary final review flow remain in use.

No live model test is implied by a successful APK build. Provider credentials and a successful real request are required to verify agent behavior with the selected model.

## What to test on the phone

These are acceptance checks for the device owner to run; they are **not claimed as completed on-device results**:

| Flow | Expected behavior |
| --- | --- |
| Open without the backend or USB reverse mapping | Arabic connection instructions and retry; no blank app or hidden payment attempt |
| Connect to the local backend | Same fictional user selection, wallet UI and model-mode label as the browser |
| Ask to send money to a duplicate contact name | Ask which contact; do not invent the recipient |
| Prepare a transfer, then leave the review | No debit until the explicit final Confirm action |
| Double-tap/retry confirmation | One mock debit and recovery of the original result |
| Switch fictional profiles | New session with that profile's data; prior owner's review cannot authorize a new debit |
| Enter a LAN HTTP address or `file:`/`javascript:` URL in native settings | Address rejected |
| Choose a different trusted backend | Existing cookies/storage/cache cleared before loading that origin |
| HTTPS certificate error | Connection fails closed; no bypass button |
| Rotate, open the keyboard, and enable large text | Arabic controls and final review remain readable; verify on the actual target device |

## Remote HTTPS option

Native settings also accept a bare HTTPS origin, for example `https://demo.example/`. The app asks before switching to a new remote origin because the UI and conversations will use that server. This is an advanced option for a backend you operate and trust; **no hosted backend is included**.

The current local Python server rejects foreign Host/Origin values. A remote HTTPS deployment therefore requires explicit server configuration, an authenticated reverse proxy, transport/cookie settings and access controls; entering a URL in the APK does not perform that deployment. The supported test workflow above needs none of those changes. Never expose the unauthenticated demo profile selector publicly as if it were production login.

## Build from source

The small shell uses Android platform APIs with no third-party Android dependencies. The Python build script uses the official SDK's `aapt2`, `d8`, `zipalign` and `apksigner`; it does not need Gradle. Install a JDK 17+ (including the compiler module), Python 3.12+, and these official SDK packages:

```bash
sdkmanager "platforms;android-35" "build-tools;35.0.0" "platform-tools"
```

Then run the build script, replacing the SDK path with your installation:

```bash
python scripts/build_android.py --sdk /path/to/Android/Sdk
```

On Windows, pass a quoted Windows SDK path. `java` and `keytool` must be on PATH,
or pass `--jdk "C:\path\to\jdk"` for a portable JDK without changing system
settings. `READY_ANDROID_SDK` can be used instead of `--sdk`; `JAVA_HOME` is the
default for `--jdk` when present. Install the required SDK packages and personally
review/accept their licenses through the official Android tools. The build script
does not download tools, accept licenses or change machine-wide settings.

Outputs:

- `android/build/outputs/AliDheaa_Topic04_READY_Debug.apk`
- `android/build/outputs/build-info.json` with the APK SHA-256, size, actual manifest
  version/package/API levels, source commit/branch/dirty-tree status, Android-source
  fingerprint, Java version, endpoint test result and signature verification.

The script performs the Java endpoint-policy assertions, compiles Java/resources/DEX,
aligns and signs the package, verifies its signature, checks the declared manifest,
and validates ZIP integrity plus DEX header, hashes and table bounds. These structural
checks do not establish on-device execution. Each build uses a new ignored
`android/build/run-*` directory; it no longer deletes previous builds. The latest
verified files are copied to `android/build/outputs/`. A prior convenience copy is
preserved under the new run's `previous-outputs/` before replacement. A failed build
before publication leaves the previous artifact intact.

An existing debug signing key is reused from ignored `android/.local/debug.keystore`;
a new key is created only when absent. Neither keys nor SDK/build outputs are committed.
Debug builds using different keys cannot update one another with `adb install -r`.
If a signature conflict appears, preserve the previous APK/key and explain the choice:
use the matching key to keep app state, or obtain the owner's approval before uninstalling
the old test app. Uninstalling clears client settings; never do it silently.

This is a signed **debug test build**, not a Play Store or production release. No emulator or physical Android device was available during the initial build, so installation, runtime WebView behavior and phone layout still need the device acceptance checks above.

## Current Windows rebuild — 22 October 2026

The following entry is historical; the 23 October rebuild above is the current
local artifact.

The project-local official SDK/JDK rebuild completed from clean commit
`98f40f953119e7d101a34c120b7ada8589c3caa4`. The resulting package is
`iq.ready.billpay.demo`, version `0.2.0-demo`, 33,326 bytes. Its SHA-256 is
`356ec0596e0f3c5aa358ade931685ed5da58e29cfcbb6ab7fa17330db62a05d5`.
The signed APK uses v2/v3, passes 16-KiB alignment and structural DEX checks,
and passed 38 native endpoint-policy assertions. The matching ignored local
debug key and full build metadata remain beside the APK; this does not claim
an install or runtime check on a phone.

## Initial build tool provenance

Initial compilation used Java 17.0.20, Android platform 35 revision 2, and SDK Build Tools 35.0.0. Official SDK archives were checked against the checksums in Google's SDK repository metadata before extraction:

| Official archive | SHA-1 from Google's package metadata |
| --- | --- |
| [platform-35_r02.zip](https://dl.google.com/android/repository/platform-35_r02.zip) | `0bb560a90a7a2cbd0dd8348224d518b638fe7949` |
| [build-tools_r35_linux.zip](https://dl.google.com/android/repository/build-tools_r35_linux.zip) | `2cfaa0bbb2336e9ec18ed3ecea84fa2e2af607bc` |
| [platform-tools_r37.0.1-linux.zip](https://dl.google.com/android/repository/platform-tools_r37.0.1-linux.zip) | `477254aa5f903c15cf51001717bdf347fb6b53e0` |

These are SDK supply metadata, not APK hashes. The precise hash of each generated APK is recorded in its `build-info.json`. Future builds can have different APK hashes because debug signing keys and ZIP timestamps differ.

## Native boundary

The shell validates scheme, host and effective port as an exact origin. It blocks navigation outside the configured backend, intercepts foreign resource requests, disables file/content access, third-party cookies and mixed content, and exposes no JavaScript/native bridge. TLS errors are cancelled. Android network security configuration permits cleartext only for `127.0.0.1` and `localhost`. The backend's content security policy and authorization remain necessary; the WebView shell is not a replacement for server controls or production authentication.

Only `INTERNET` is requested. There is no camera, microphone, contacts, storage or payment permission. All model calls run server-side. This client is independent and is not an official ZainCash application.

## Official references

- [WebView](https://developer.android.com/develop/ui/views/layout/webapps/webview)
- [Network security configuration](https://developer.android.com/privacy-and-security/security-config)
- [Unsafe URI loading](https://developer.android.com/privacy-and-security/risks/unsafe-uri-loading)
- [WebView native bridge risks](https://developer.android.com/privacy-and-security/risks/insecure-webview-native-bridges)
- [Android Debug Bridge](https://developer.android.com/tools/adb)
- [AAPT2](https://developer.android.com/tools/aapt2), [D8](https://developer.android.com/tools/d8), [APK signing](https://developer.android.com/tools/apksigner)
- [SDK repository package metadata](https://dl.google.com/android/repository/repository2-1.xml)
- [SDK package-license acceptance](https://developer.android.com/tools/sdkmanager#accept-licenses)
- [DEX format](https://source.android.com/docs/core/runtime/dex-format)
