# Installing UEE Mobile Garage Permits (macOS)

This guide is for staff receiving the app. If you're looking for build
instructions instead, see `tools/build_macos.sh`.

## Requirements

- **Apple Silicon Mac** (M1, M2, M3, M4 — any 2020-or-later Mac).
  Intel Macs are not supported by this build.
- macOS 13 (Ventura) or newer.

## Install

1. Download `UEEMobileGaragePermits.zip` from Box.
2. Double-click the zip to extract `UEEMobileGaragePermits.app`.
3. Drag `UEEMobileGaragePermits.app` to your **Applications** folder
   (or anywhere — Desktop works too).

## First launch

Because the app isn't notarized through Apple's paid developer program,
macOS will block it the first time. The fix takes one click:

1. **Right-click** (or Control-click) `UEEMobileGaragePermits.app`.
2. Choose **Open** from the menu.
3. A dialog appears warning the app is from an unidentified developer.
   Click **Open**.

macOS remembers the choice — every launch after the first is just a
normal double-click.

### If macOS says the app is "damaged and can't be opened"

Newer macOS versions sometimes refuse to open downloaded apps with the
"damaged" message even after right-clicking. To clear that, open
**Terminal** (Applications → Utilities → Terminal) and run:

```bash
xattr -dr com.apple.quarantine /Applications/UEEMobileGaragePermits.app
```

Adjust the path if the app is somewhere other than `/Applications/`.
Then double-click the app as normal.

## Where output PDFs go

When you process a permit batch with event name `My Event`, the app
creates a folder named `My Event` next to the `.app` itself, and writes
each split permit PDF inside. Example:

```
~/Applications/
├── UEEMobileGaragePermits.app
└── My Event/
    ├── SJG_XXAB1234567.pdf
    └── SAG_XXAB1234568.pdf
```

If you keep the app in `/Applications/`, output goes there too.

## Troubleshooting

**The app won't open and just bounces in the Dock.** Try removing the
quarantine attribute (see above). If that doesn't fix it, open
**Console.app** (Applications → Utilities), filter for
`UEEMobileGaragePermits`, and copy the most recent error to share.

**OCR didn't extract a field correctly.** The app uses Tesseract OCR,
which is bundled inside the `.app`. Try a higher-quality scan of the
permit. Garage permits work; surface lot permits (e.g. "Lot 80") are
not supported by this tool.

**Drag-and-drop doesn't work.** Click the drop zone instead — it opens
a file browser.

## What's bundled

The `.app` is fully self-contained — recipients do **not** need to
install Homebrew, Tesseract, Poppler, or Python. Everything ships
inside the bundle.
