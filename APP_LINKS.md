# Android App Links

Shared post URLs should use the public domain:

- `https://gaji.run/indexdetail.html?id=...`
- `https://gaji.run/boarddetail.html?id=...`

The Android app now has intent filters for these `https://gaji.run` URLs. To make Android open the app directly without a chooser, publish an `assetlinks.json` file after the final signing certificate is known.

Create this file at:

```text
https://gaji.run/.well-known/assetlinks.json
```

Use this shape and replace `SHA256_CERT_FINGERPRINT` with the Play App Signing SHA-256 certificate fingerprint:

```json
[
  {
    "relation": ["delegate_permission/common.handle_all_urls"],
    "target": {
      "namespace": "android_app",
      "package_name": "com.namin.gaji.run",
      "sha256_cert_fingerprints": [
        "SHA256_CERT_FINGERPRINT"
      ]
    }
  }
]
```

Until this file is published with the real fingerprint, Android may show an app/browser chooser even though the app can handle the link.
