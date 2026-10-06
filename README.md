# Marketing DAM App

This project is a pure Python digital asset management (DAM) system for marketing teams. It allows designers to upload brand assets and enables brand managers to review, approve, and reject them before use.

## Features

- Sign up and log in with separate admin and user roles
- Reveal or hide passwords and reset to a new password
- Upload graphics, logos, vector files, and other marketing assets with descriptions
- Store uploaded files in a local asset directory
- Track asset IDs, names, descriptions, categories, file paths, uploaders, dates, and statuses
- Review queue with filtering, admin approval/rejection, comments, and review history
- Record approved use, expiration dates, and restrictions for each asset
- Log out and return to the sign-in screen
- Local JSON persistence in `assets_data.json`; uploaded files are stored in `uploaded_assets/`

## Run the app

1. Open a terminal in this folder.
2. Run:

```bash
python main.py
```

## Files created

- `main.py` - main application GUI
- `assets_data.json` - asset records saved locally
- `uploaded_assets/` - uploaded files are copied here

## Notes

This is a demonstration app built using the Python standard library. It uses `tkinter` for the desktop interface and JSON for storage. A first run seeds an administrator account: `admin@dam.local` / `admin123`. Change that demo password after signing in before using the app with real data.
