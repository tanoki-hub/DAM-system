import hashlib
import hmac
import json
import os
import secrets
import shutil
import uuid
from datetime import datetime
from pathlib import Path

import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk


APP_NAME = "Marketing DAM System"
BASE_DIR = Path(__file__).resolve().parent
UPLOADS_DIR = BASE_DIR / "uploaded_assets"


class DataStore:
    def __init__(self, data_path=None):
        self.data_path = Path(data_path) if data_path else BASE_DIR / "assets_data.json"
        self.data_path.parent.mkdir(parents=True, exist_ok=True)
        self.data = self._load()
        if not any(user.get("role") == "admin" for user in self.data["users"]):
            self.register_user("System Administrator", "admin@dam.local", "admin123", "admin")

    def _load(self):
        if not self.data_path.exists():
            return {"users": [], "assets": [], "reviews": [], "usage_rights": []}
        try:
            with self.data_path.open("r", encoding="utf-8") as data_file:
                data = json.load(data_file)
        except (OSError, json.JSONDecodeError):
            data = {}
        for key in ("users", "assets", "reviews", "usage_rights"):
            if not isinstance(data.get(key), list):
                data[key] = []
        migrated = False
        for user in data["users"]:
            if "user_id" not in user:
                user["user_id"] = f"USER-{uuid.uuid4().hex[:8].upper()}"
                migrated = True
            if "password_hash" not in user:
                legacy_password = user.pop("password", "")
                user["password_hash"] = self._hash_password(legacy_password) if legacy_password else ""
                migrated = True
            if "password_hint" in user:
                user.pop("password_hint")
                migrated = True
            user.setdefault("created_at", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
            user["email"] = user.get("email", "").strip().lower()
        if migrated:
            self._save_data(data)
        return data

    @staticmethod
    def _hash_password(password, salt=None):
        salt = salt or secrets.token_hex(16)
        digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt), 200000).hex()
        return f"{salt}${digest}"

    @staticmethod
    def _public_user(user):
        return {key: value for key, value in user.items() if key != "password_hash"}

    def _save_data(self, data=None):
        payload = self.data if data is None else data
        temporary_path = self.data_path.with_suffix(self.data_path.suffix + ".tmp")
        with temporary_path.open("w", encoding="utf-8") as data_file:
            json.dump(payload, data_file, indent=2)
        temporary_path.replace(self.data_path)

    def list_users(self):
        return [self._public_user(user) for user in self.data["users"]]

    def get_user(self, user_id):
        user = next((item for item in self.data["users"] if item["user_id"] == user_id), None)
        return self._public_user(user) if user else None

    def get_user_by_email(self, email):
        normalized_email = (email or "").strip().lower()
        user = next((item for item in self.data["users"] if item["email"] == normalized_email), None)
        return user

    def register_user(self, name, email, password, role="user"):
        name = (name or "").strip()
        email = (email or "").strip().lower()
        if not name or not email or not password:
            raise ValueError("Name, email, and password are required.")
        if role not in ("admin", "user"):
            raise ValueError("Role must be admin or user.")
        if self.get_user_by_email(email):
            raise ValueError("An account with this email already exists.")
        user = {
            "user_id": f"USER-{uuid.uuid4().hex[:8].upper()}",
            "name": name,
            "email": email,
            "password_hash": self._hash_password(password),
            "role": role,
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        self.data["users"].append(user)
        self._save_data()
        return self._public_user(user)

    def authenticate(self, email, password):
        user = self.get_user_by_email(email)
        if not user or "$" not in user.get("password_hash", ""):
            return None
        salt, expected_hash = user["password_hash"].split("$", 1)
        actual_hash = self._hash_password(password, salt).split("$", 1)[1]
        return self._public_user(user) if hmac.compare_digest(actual_hash, expected_hash) else None

    def reset_password(self, email, new_password):
        user = self.get_user_by_email(email)
        if not user:
            return False
        if not new_password:
            raise ValueError("A new password is required.")
        user["password_hash"] = self._hash_password(new_password)
        self._save_data()
        return True

    def add_asset(self, asset_name, description, category, file_path, uploaded_by, submission_notes=""):
        user = next((item for item in self.data["users"] if item["user_id"] == uploaded_by), None)
        if not user:
            raise ValueError("The uploading user does not exist.")
        asset = {
            "asset_id": f"ASSET-{uuid.uuid4().hex[:8].upper()}",
            "asset_name": (asset_name or "").strip(),
            "description": (description or "").strip(),
            "submission_notes": (submission_notes or "").strip(),
            "category": (category or "").strip(),
            "file_path": str(file_path),
            "uploaded_by": uploaded_by,
            "uploaded_by_name": user["name"],
            "uploaded_by_email": user["email"],
            "upload_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "status": "Pending Review",
        }
        self.data["assets"].append(asset)
        self._save_data()
        return dict(asset)

    def list_assets(self, user_id=None, role="user"):
        assets = self.data["assets"]
        if role != "admin":
            assets = [asset for asset in assets if asset.get("uploaded_by") == user_id]
        return [dict(asset) for asset in assets]

    def add_review(self, asset_id, reviewer_id, decision, comments=""):
        if decision not in ("Approved", "Rejected"):
            raise ValueError("Decision must be Approved or Rejected.")
        asset = next((item for item in self.data["assets"] if item["asset_id"] == asset_id), None)
        reviewer = next((item for item in self.data["users"] if item["user_id"] == reviewer_id), None)
        if not asset or not reviewer:
            raise ValueError("Asset and reviewer must exist.")
        review = {
            "review_id": f"REVIEW-{uuid.uuid4().hex[:8].upper()}",
            "asset_id": asset_id,
            "reviewer_id": reviewer_id,
            "decision": decision,
            "comments": (comments or "").strip(),
            "review_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        self.data["reviews"].append(review)
        asset["status"] = decision
        asset["review_notes"] = review["comments"]
        self._save_data()
        return dict(review)

    def list_reviews(self, asset_id=None):
        reviews = self.data["reviews"]
        if asset_id:
            reviews = [review for review in reviews if review["asset_id"] == asset_id]
        return [dict(review) for review in reviews]

    def add_usage_right(self, asset_id, approved_for, expiration_date="", restrictions=""):
        if not any(item["asset_id"] == asset_id for item in self.data["assets"]):
            raise ValueError("Asset not found.")
        right = {
            "rights_id": f"RIGHTS-{uuid.uuid4().hex[:8].upper()}",
            "asset_id": asset_id,
            "approved_for": (approved_for or "").strip(),
            "expiration_date": (expiration_date or "").strip(),
            "restrictions": (restrictions or "").strip(),
        }
        self.data["usage_rights"].append(right)
        self._save_data()
        return dict(right)

    def list_usage_rights(self, asset_id=None):
        rights = self.data["usage_rights"]
        if asset_id:
            rights = [right for right in rights if right["asset_id"] == asset_id]
        return [dict(right) for right in rights]


APP_STORE = None


def init_db():
    global APP_STORE
    APP_STORE = DataStore()


def create_user(name, email, password, role):
    try:
        APP_STORE.register_user(name, email, password, role)
    except ValueError as error:
        return {"success": False, "message": str(error)}
    return {"success": True, "message": "Account created successfully."}


def get_user_by_email(email):
    user = APP_STORE.get_user_by_email(email)
    return APP_STORE._public_user(user) if user else None


def authenticate_user(email, password):
    return APP_STORE.authenticate(email, password)


def reset_password(email, new_password):
    try:
        reset = APP_STORE.reset_password(email, new_password)
    except ValueError as error:
        return {"success": False, "message": str(error)}
    if not reset:
        return {"success": False, "message": "No account found for this email."}
    return {"success": True, "message": "Password reset successfully."}


def load_assets_for_user(user_email, role):
    user = APP_STORE.get_user_by_email(user_email)
    user_id = user["user_id"] if user else None
    assets = APP_STORE.list_assets(user_id, role)
    return [
        {
            **asset,
            "id": asset["asset_id"],
            "title": asset["asset_name"],
            "uploader_name": asset.get("uploaded_by_name", ""),
            "uploader_email": asset.get("uploaded_by_email", ""),
            "file_name": Path(asset["file_path"]).name,
            "stored_path": asset["file_path"],
            "uploaded_at": asset["upload_date"],
            "review_notes": asset.get("review_notes", ""),
        }
        for asset in assets
    ]


def save_asset(asset_data):
    return APP_STORE.add_asset(
        asset_name=asset_data["title"],
        description=asset_data.get("description", ""),
        category=asset_data["category"],
        file_path=asset_data["stored_path"],
        uploaded_by=asset_data["uploaded_by"],
        submission_notes=asset_data.get("review_notes", ""),
    )


def update_asset_status(asset_id, new_status, new_notes, reviewer_id):
    APP_STORE.add_review(asset_id, reviewer_id, new_status, new_notes)


class LoginApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_NAME)
        self.geometry("840x440")
        self.minsize(760, 390)
        self.configure(bg="#0ca2e7")

        init_db()
        self.apply_professional_theme()

        container = tk.Frame(self, bg="#0ca2e7", padx=12, pady=12)
        container.pack(fill="both", expand=True)

        shell = tk.Frame(container, bg="#f3f4f8", width=760, height=400)
        shell.pack(fill="both", expand=True)
        shell.pack_propagate(False)

        left_panel = tk.Frame(shell, bg="#0ca2e7", width=300, height=400)
        left_panel.pack(side="left", fill="y")
        left_panel.pack_propagate(False)

        left_canvas = tk.Canvas(left_panel, bg="#0ca2e7", width=430, height=520, highlightthickness=0)
        left_canvas.pack(fill="both", expand=True)
        left_canvas.create_oval(-150, 420, 220, 760, fill="#0a8fd8", outline="")
        left_canvas.create_oval(145, 360, 480, 760, fill="#0a8fd8", outline="")
        left_canvas.create_oval(220, 260, 650, 720, fill="#0a8fd8", outline="")

        tk.Label(left_panel, text="MARKETING ASSET HUB", fg="#ffffff", bg="#0ca2e7", font=("Arial", 14, "bold")).place(x=28, y=28)
        tk.Label(
            left_panel,
            text="Empower your marketing teams to organize, store, and share brand assets seamlessly. Eliminate search time and keep your brand consistent across every channel.",
            fg="#dfefff",
            bg="#0ca2e7",
            font=("Arial", 9),
            justify="left",
            wraplength=230,
        ).place(x=28, y=88)

        right_panel = tk.Frame(shell, bg="#f3f4f8", width=460, height=400)
        right_panel.pack(side="left", fill="both", expand=True)
        right_panel.pack_propagate(False)

        self.login_email_var = tk.StringVar()
        self.login_password_var = tk.StringVar()
        self.signup_name_var = tk.StringVar()
        self.signup_email_var = tk.StringVar()
        self.signup_password_var = tk.StringVar()
        self.signup_role_var = tk.StringVar(value="user")

        tab_control = ttk.Notebook(right_panel)
        tab_control.pack(fill="x", padx=18, pady=(12, 8))

        login_frame = tk.Frame(tab_control, bg="#f3f4f8", padx=8, pady=8)
        signup_frame = tk.Frame(tab_control, bg="#f3f4f8", padx=8, pady=8)

        tab_control.add(login_frame, text="Log In")
        tab_control.add(signup_frame, text="Sign Up")

        login_form = tk.Frame(login_frame, bg="#f3f4f8")
        login_form.pack(fill="x")

        tk.Label(login_form, text="Sign in", bg="#f3f4f8", fg="#1d2736", font=("Arial", 25, "bold")).pack(anchor="w", pady=(4, 10))

        user_row = tk.Frame(login_form, bg="#f3f4f8")
        user_row.pack(fill="x", pady=(0, 8))
        tk.Label(user_row, text="👤", bg="#f3f4f8", fg="#4b5360", font=("Arial", 13)).pack(side="left", padx=(0, 8), pady=8)
        tk.Entry(
            user_row,
            textvariable=self.login_email_var,
            bg="#ffffff",
            fg="#1f232b",
            font=("Arial", 11),
            bd=1,
            relief="solid",
            highlightbackground="#ccd4de",
            highlightthickness=1,
            insertbackground="#1f232b",
        ).pack(side="left", fill="x", expand=True, ipady=6)

        password_row = tk.Frame(login_form, bg="#f3f4f8")
        password_row.pack(fill="x", pady=(0, 8))
        tk.Label(password_row, text="🔒", bg="#f3f4f8", fg="#4b5360", font=("Arial", 13)).pack(side="left", padx=(0, 8), pady=8)
        self.login_password_entry = tk.Entry(
            password_row,
            textvariable=self.login_password_var,
            show="*",
            bg="#ffffff",
            fg="#1f232b",
            font=("Arial", 11),
            bd=1,
            relief="solid",
            highlightbackground="#ccd4de",
            highlightthickness=1,
            insertbackground="#1f232b",
        )
        self.login_password_entry.pack(side="left", fill="x", expand=True, ipady=6)
        self.login_password_toggle = tk.Button(
            password_row,
            text="SHOW",
            command=lambda: self.toggle_password_visibility(self.login_password_entry, self.login_password_toggle),
            bg="#f3f4f8",
            fg="#6a7687",
            bd=0,
            activebackground="#edf0f3",
            font=("Arial", 7, "bold"),
            width=5,
        )
        self.login_password_toggle.pack(side="left", padx=(8, 0))

        options_row = tk.Frame(login_form, bg="#f3f4f8")
        options_row.pack(fill="x", pady=(0, 8))
        tk.Checkbutton(options_row, text="Remember me", bg="#f3f4f8", fg="#5d6976", font=("Arial", 8), activebackground="#f3f4f8").pack(side="left")
        tk.Label(options_row, text="Forgot Password?", bg="#f3f4f8", fg="#0b67d9", font=("Arial", 8, "bold")).pack(side="right")

        tk.Button(
            login_form,
            text="Sign in",
            command=self.login_user,
            bg="#0b67d9",
            fg="white",
            activebackground="#095ac5",
            activeforeground="white",
            bd=0,
            font=("Arial", 12, "bold"),
            pady=8,
            width=26,
        ).pack(fill="x", pady=(6, 8))

        signup_form = tk.Frame(signup_frame, bg="#f3f4f8")
        signup_form.pack(fill="x")

        tk.Label(signup_form, text="Full Name", bg="#f5f7fa", fg="#3b4451", font=("Arial", 9, "bold")).pack(anchor="w", pady=(0, 4))
        tk.Entry(signup_form, textvariable=self.signup_name_var, bg="#ffffff", fg="#1f232b", font=("Arial", 10), bd=1, relief="solid", highlightbackground="#cfd6df", highlightthickness=1, insertbackground="#1f232b").pack(fill="x", ipady=4)

        tk.Label(signup_form, text="Email", bg="#f5f7fa", fg="#3b4451", font=("Arial", 9, "bold")).pack(anchor="w", pady=(8, 4))
        tk.Entry(signup_form, textvariable=self.signup_email_var, bg="#ffffff", fg="#1f232b", font=("Arial", 10), bd=1, relief="solid", highlightbackground="#cfd6df", highlightthickness=1, insertbackground="#1f232b").pack(fill="x", ipady=4)

        tk.Label(signup_form, text="Password", bg="#f5f7fa", fg="#3b4451", font=("Arial", 9, "bold")).pack(anchor="w", pady=(8, 4))
        tk.Entry(signup_form, textvariable=self.signup_password_var, show="*", bg="#ffffff", fg="#1f232b", font=("Arial", 10), bd=1, relief="solid", highlightbackground="#cfd6df", highlightthickness=1, insertbackground="#1f232b").pack(fill="x", ipady=4)

        tk.Label(signup_form, text="Role", bg="#f5f7fa", fg="#3b4451", font=("Arial", 9, "bold")).pack(anchor="w", pady=(8, 4))
        role_combo = ttk.Combobox(
            signup_form,
            textvariable=self.signup_role_var,
            values=["User", "Admin"],
            state="readonly",
            width=28,
            font=("Arial", 10),
        )
        role_combo.pack(fill="x", ipady=2)
        role_combo.current(0)

        tk.Button(
            signup_form,
            text="Create Account",
            command=self.signup_user,
            bg="#0b67d9",
            fg="white",
            activebackground="#095ac5",
            activeforeground="white",
            bd=0,
            font=("Arial", 11, "bold"),
            pady=7,
            width=28,
        ).pack(fill="x", pady=(10, 0))

        self.login_email_var.set("")
        self.login_password_var.set("")
        self.signup_name_var.set("")
        self.signup_email_var.set("")
        self.signup_password_var.set("")

    def apply_professional_theme(self):
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except Exception:
            pass
        style.configure("TNotebook", background="#f4f4f4", borderwidth=0)
        style.configure("TNotebook.Tab", padding=(10, 8), background="#e8e8e8", foreground="#4d5665", font=("Arial", 9, "bold"), borderwidth=0)
        style.map("TNotebook.Tab", background=[("selected", "#f4f4f4")], foreground=[("selected", "#1f232b")])
        style.configure("TCombobox", padding=(8, 4), fieldbackground="#ffffff")

    def login_user(self):
        email = self.login_email_var.get().strip()
        password = self.login_password_var.get().strip()

        if not email or not password:
            messagebox.showwarning("Missing credentials", "Please enter your email and password.")
            return

        user = authenticate_user(email, password)
        if user is None:
            messagebox.showerror("Login failed", "Invalid email or password.")
            return

        self.destroy()
        DAMApp(user).mainloop()

    @staticmethod
    def toggle_password_visibility(entry, button):
        is_hidden = entry.cget("show") == "*"
        entry.configure(show="" if is_hidden else "*")
        button.configure(text="Hide" if is_hidden else "Show")

    def signup_user(self):
        name = self.signup_name_var.get().strip()
        email = self.signup_email_var.get().strip().lower()
        password = self.signup_password_var.get().strip()
        role = self.signup_role_var.get().strip().lower()
        result = create_user(name, email, password, role)
        if not result["success"]:
            messagebox.showwarning("Sign up failed", result["message"])
            return

        messagebox.showinfo("Account created", f"Your {role} account was created successfully.")
        self.signup_name_var.set("")
        self.signup_email_var.set("")
        self.signup_password_var.set("")
        self.signup_role_var.set("user")

    def forgot_password(self):
        email = simpledialog.askstring("Reset password", "Enter your email to reset your password:")
        if not email:
            return

        user = get_user_by_email(email)
        if not user:
            messagebox.showwarning("Reset failed", "No account found for this email.")
            return
        new_password = simpledialog.askstring("Choose a new password", "Enter your new password:", show="*")
        if not new_password:
            return
        confirmation = simpledialog.askstring("Confirm password", "Enter the new password again:", show="*")
        if confirmation != new_password:
            messagebox.showwarning("Reset failed", "The passwords did not match.")
            return
        result = reset_password(email, new_password)
        if result["success"]:
            messagebox.showinfo("Password reset", result["message"])
        else:
            messagebox.showwarning("Reset failed", result["message"])


class DAMApp(tk.Tk):
    def __init__(self, user):
        super().__init__()
        self.current_user = user
        self.title(APP_NAME)
        self.geometry("1250x760")
        self.minsize(1040, 680)
        self.configure(bg="#eff6ff")

        self.selected_file_path = ""
        self.current_filter = "All"
        self.review_note_var = tk.StringVar()
        self.apply_professional_theme()

        self._build_ui()
        self.refresh_asset_list()

    def apply_professional_theme(self):
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except Exception:
            pass
        style.configure("Treeview", rowheight=30, font=("Arial", 10), background="#ffffff", foreground="#0f172a", fieldbackground="#ffffff")
        style.configure("Treeview.Heading", font=("Arial", 10, "bold"), background="#e2e8f0", foreground="#0f172a")
        style.map("Treeview", background=[("selected", "#dbeafe")], foreground=[("selected", "#0f172a")])

    def _build_ui(self):
        top_bar = tk.Frame(self, bg="#0f172a", padx=24, pady=18)
        top_bar.pack(fill="x")

        tk.Button(top_bar, text="Log out", command=self.logout, bg="#334155", fg="#ffffff", activebackground="#475569", bd=0, padx=12, pady=7).pack(side="right")
        tk.Label(top_bar, text="Digital Asset Management", fg="#ffffff", bg="#0f172a", font=("Arial", 20, "bold")).pack(anchor="w")
        tk.Label(
            top_bar,
            text=f"{self.current_user['name']} • {self.current_user['role'].title()} access",
            fg="#cbd5e1",
            bg="#0f172a",
            font=("Arial", 10),
        ).pack(anchor="w", pady=(4, 0))

        summary_bar = tk.Frame(self, bg="#eff6ff", padx=18, pady=16)
        summary_bar.pack(fill="x")

        cards = [
            ("Pending Review", self.count_status("Pending Review"), "#f59e0b"),
            ("Approved", self.count_status("Approved"), "#22c55e"),
            ("Rejected", self.count_status("Rejected"), "#ef4444"),
        ]

        for title, value, color in cards:
            card = tk.Frame(summary_bar, bg="#ffffff", highlightbackground="#dfe7f5", highlightthickness=1, padx=16, pady=14)
            card.pack(side="left", expand=True, fill="x", padx=(0, 12))
            tk.Label(card, text=title, fg="#64748b", bg="#ffffff", font=("Arial", 10, "bold")).pack(anchor="w")
            tk.Label(card, text=str(value), fg=color, bg="#ffffff", font=("Arial", 24, "bold")).pack(anchor="w", pady=(6, 0))

        main = tk.Frame(self, padx=18, pady=18, bg="#eff6ff")
        main.pack(fill="both", expand=True)

        left_panel = tk.Frame(main, bg="#ffffff", bd=0, highlightbackground="#dfe7f5", highlightthickness=1, padx=18, pady=18)
        left_panel.pack(side="left", fill="y", padx=(0, 14))

        upload_canvas = tk.Canvas(left_panel, bg="#ffffff", highlightthickness=0, width=300)
        upload_scrollbar = ttk.Scrollbar(left_panel, orient="vertical", command=upload_canvas.yview)
        upload_form = tk.Frame(upload_canvas, bg="#ffffff")
        upload_form.bind("<Configure>", lambda event: upload_canvas.configure(scrollregion=upload_canvas.bbox("all")))
        upload_canvas.create_window((0, 0), window=upload_form, anchor="nw", tags="upload_form")
        upload_canvas.configure(yscrollcommand=upload_scrollbar.set)
        upload_canvas.bind("<Configure>", lambda event: upload_canvas.itemconfigure("upload_form", width=event.width))
        upload_canvas.pack(side="left", fill="both", expand=True)
        upload_scrollbar.pack(side="right", fill="y")

        tk.Label(upload_form, text="Upload Asset", fg="#0f172a", bg="#ffffff", font=("Arial", 16, "bold")).pack(anchor="w")
        tk.Label(upload_form, text="Add a new marketing file for review and compliance approval.", fg="#64748b", bg="#ffffff", font=("Arial", 10), justify="left", wraplength=290).pack(anchor="w", pady=(4, 12))

        self.title_var = tk.StringVar()
        self.category_var = tk.StringVar(value="Brand Graphic")
        self.file_label_var = tk.StringVar(value="No file selected")
        self.approved_for_var = tk.StringVar()
        self.expiration_date_var = tk.StringVar()
        self.restrictions_var = tk.StringVar()

        tk.Label(upload_form, text="Asset Title", font=("Arial", 10, "bold"), fg="#0f172a", bg="#ffffff").pack(anchor="w", pady=(10, 4))
        tk.Entry(upload_form, textvariable=self.title_var, width=34, font=("Arial", 11), bd=1, relief="solid").pack(fill="x")

        tk.Label(upload_form, text="Description", font=("Arial", 10, "bold"), fg="#0f172a", bg="#ffffff").pack(anchor="w", pady=(8, 4))
        self.description_box = tk.Text(upload_form, height=2, width=34, font=("Arial", 10), bd=1, relief="solid")
        self.description_box.pack(fill="x")

        tk.Label(upload_form, text="Category", font=("Arial", 10, "bold"), fg="#0f172a", bg="#ffffff").pack(anchor="w", pady=(14, 4))
        ttk.Combobox(
            upload_form,
            textvariable=self.category_var,
            values=["Brand Graphic", "Logo", "Social Media", "Website Banner", "Video Thumbnail", "Packaging"],
            state="readonly",
            width=31,
        ).pack(fill="x")

        tk.Label(upload_form, text="File", font=("Arial", 10, "bold"), fg="#0f172a", bg="#ffffff").pack(anchor="w", pady=(14, 4))
        upload_row = tk.Frame(upload_form, bg="#ffffff")
        upload_row.pack(fill="x")
        tk.Entry(upload_row, textvariable=self.file_label_var, state="readonly", width=24, font=("Arial", 10), bd=1, relief="solid").pack(side="left", fill="x", expand=True)
        tk.Button(upload_row, text="Browse", command=self.browse_file, bg="#dbeafe", fg="#0f172a", activebackground="#bfdbfe", bd=0, padx=12, pady=6).pack(side="left", padx=(8, 0))

        tk.Label(upload_form, text="Usage Rights (optional)", font=("Arial", 10, "bold"), fg="#0f172a", bg="#ffffff").pack(anchor="w", pady=(10, 4))
        rights_fields = [
            ("Approved for", self.approved_for_var),
            ("Expiration date", self.expiration_date_var),
            ("Restrictions", self.restrictions_var),
        ]
        for label, variable in rights_fields:
            rights_row = tk.Frame(upload_form, bg="#ffffff")
            rights_row.pack(fill="x", pady=(0, 3))
            tk.Label(rights_row, text=label, width=13, anchor="w", bg="#ffffff", fg="#475569", font=("Arial", 8)).pack(side="left")
            tk.Entry(rights_row, textvariable=variable, font=("Arial", 9), bd=1, relief="solid").pack(side="left", fill="x", expand=True)

        tk.Label(upload_form, text="Review Notes", font=("Arial", 10, "bold"), fg="#0f172a", bg="#ffffff").pack(anchor="w", pady=(8, 4))
        notes_box = tk.Text(upload_form, height=2, width=34, font=("Arial", 10), bd=1, relief="solid")
        notes_box.pack(fill="x")

        tk.Button(
            upload_form,
            text="Upload Asset",
            command=lambda: self.create_asset(
                notes_box.get("1.0", "end").strip(),
                self.description_box.get("1.0", "end").strip(),
            ),
            bg="#2563eb",
            fg="white",
            activebackground="#1d4ed8",
            bd=0,
            padx=18,
            pady=10,
            width=18,
            font=("Arial", 10, "bold"),
        ).pack(pady=(18, 0))

        right_panel = tk.Frame(main, bg="#ffffff", bd=0, highlightbackground="#dfe7f5", highlightthickness=1, padx=16, pady=16)
        right_panel.pack(side="left", fill="both", expand=True)

        top_right = tk.Frame(right_panel, bg="#ffffff")
        top_right.pack(fill="x")
        tk.Label(top_right, text="Review Queue", bg="#ffffff", fg="#0f172a", font=("Arial", 16, "bold")).pack(anchor="w")

        filter_row = tk.Frame(top_right, bg="#ffffff")
        filter_row.pack(fill="x", pady=(10, 12))
        tk.Label(filter_row, text="Filter by status:", bg="#ffffff", fg="#334155", font=("Arial", 10, "bold")).pack(side="left")
        self.filter_var = tk.StringVar(value="All")
        filter_combo = ttk.Combobox(
            filter_row,
            textvariable=self.filter_var,
            values=["All", "Pending Review", "Approved", "Rejected"],
            state="readonly",
            width=18,
        )
        filter_combo.pack(side="left", padx=(8, 0))
        filter_combo.bind("<<ComboboxSelected>>", self.on_filter_change)

        self.asset_tree = ttk.Treeview(right_panel, columns=("id", "title", "category", "uploader", "status", "file"), show="headings", height=16)
        for key, label in {
            "id": "ID",
            "title": "Title",
            "category": "Category",
            "uploader": "Uploader",
            "status": "Status",
            "file": "File",
        }.items():
            self.asset_tree.heading(key, text=label)
            self.asset_tree.column(key, anchor="w", width=150 if key not in ("title", "file") else 220)
        self.asset_tree.pack(fill="both", expand=True, pady=(0, 12))
        self.asset_tree.bind("<<TreeviewSelect>>", self.on_asset_selected)

        decision_panel = tk.Frame(right_panel, bg="#ffffff")
        decision_panel.pack(fill="x")
        tk.Label(decision_panel, text="Review Notes", bg="#ffffff", fg="#0f172a", font=("Arial", 10, "bold")).pack(anchor="w")
        tk.Entry(decision_panel, textvariable=self.review_note_var, width=90, font=("Arial", 10), bd=1, relief="solid").pack(fill="x", pady=(4, 12))

        decision_buttons = tk.Frame(decision_panel, bg="#ffffff")
        decision_buttons.pack(fill="x")
        self.approve_btn = tk.Button(decision_buttons, text="Approve", command=self.approve_asset, bg="#16a34a", fg="white",
                                    activebackground="#15803d", bd=0, padx=16, pady=8, width=12, font=("Arial", 10, "bold"))
        self.reject_btn = tk.Button(decision_buttons, text="Reject", command=self.reject_asset, bg="#dc2626", fg="white",
                                   activebackground="#b91c1c", bd=0, padx=16, pady=8, width=12, font=("Arial", 10, "bold"))

        if self.current_user["role"] == "admin":
            self.approve_btn.pack(side="left", padx=(0, 10))
            self.reject_btn.pack(side="left")
        else:
            self.approve_btn.config(state="disabled")
            self.reject_btn.config(state="disabled")
            tk.Label(decision_buttons, text="Admins only can approve or reject assets.", bg="#ffffff", fg="#475569",
                     font=("Arial", 10)).pack(side="left", padx=(10, 0))
        tk.Button(decision_buttons, text="Review History", command=self.show_review_history, bg="#e2e8f0", fg="#0f172a", bd=0, padx=10, pady=8).pack(side="right", padx=(6, 0))
        tk.Button(decision_buttons, text="Usage Rights", command=self.show_usage_rights, bg="#e2e8f0", fg="#0f172a", bd=0, padx=10, pady=8).pack(side="right")
        tk.Button(decision_buttons, text="Asset Details", command=self.show_asset_details, bg="#e2e8f0", fg="#0f172a", bd=0, padx=10, pady=8).pack(side="right", padx=(0, 6))

    def count_status(self, status):
        return sum(1 for asset in load_assets_for_user(self.current_user["email"], self.current_user["role"]) if asset.get("status") == status)

    def browse_file(self):
        file_path = filedialog.askopenfilename(
            title="Select a marketing asset",
            filetypes=[
                ("Image Files", "*.png *.jpg *.jpeg *.gif *.webp *.bmp *.svg"),
                ("Vector Files", "*.svg *.ai *.eps"),
                ("Documents", "*.pdf *.doc *.docx *.ppt *.pptx"),
                ("All Files", "*.*"),
            ],
        )
        if file_path:
            self.selected_file_path = file_path
            self.file_label_var.set(os.path.basename(file_path))

    def create_asset(self, notes, description):
        title = self.title_var.get().strip()
        category = self.category_var.get().strip()
        approved_for = self.approved_for_var.get().strip()
        expiration_date = self.expiration_date_var.get().strip()
        restrictions = self.restrictions_var.get().strip()

        if not title:
            messagebox.showwarning("Missing title", "Please add an asset title before uploading.")
            return

        if not self.selected_file_path or not os.path.exists(self.selected_file_path):
            messagebox.showwarning("No file selected", "Please choose a valid file to upload.")
            return

        if (expiration_date or restrictions) and not approved_for:
            messagebox.showwarning("Incomplete usage rights", "Enter an Approved for value when adding an expiration date or restrictions.")
            return

        UPLOADS_DIR.mkdir(exist_ok=True)
        file_name = os.path.basename(self.selected_file_path)
        new_name = f"{uuid.uuid4().hex}_{file_name}"
        destination = UPLOADS_DIR / new_name

        try:
            shutil.copy2(self.selected_file_path, destination)
        except OSError:
            messagebox.showerror("Upload failed", "The file could not be stored in the DAM folder.")
            return

        asset = {
            "id": f"ASSET-{uuid.uuid4().hex[:8].upper()}",
            "title": title,
            "description": description,
            "uploaded_by": self.current_user["user_id"],
            "uploader_name": self.current_user["name"],
            "uploader_email": self.current_user["email"],
            "category": category,
            "status": "Pending Review",
            "review_notes": notes,
            "file_name": file_name,
            "stored_path": str(destination),
            "uploaded_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }

        stored_asset = save_asset(asset)
        if approved_for:
            APP_STORE.add_usage_right(stored_asset["asset_id"], approved_for, expiration_date, restrictions)
        self.description_box.delete("1.0", "end")
        self.title_var.set("")
        self.category_var.set("Brand Graphic")
        self.file_label_var.set("No file selected")
        self.selected_file_path = ""
        self.review_note_var.set("")
        self.approved_for_var.set("")
        self.expiration_date_var.set("")
        self.restrictions_var.set("")
        self.refresh_asset_list()
        messagebox.showinfo("Asset uploaded", "Your asset has been uploaded and is awaiting review.")

    def on_filter_change(self, event=None):
        self.current_filter = self.filter_var.get()
        self.refresh_asset_list()

    def on_asset_selected(self, event=None):
        selected = self.asset_tree.selection()
        if not selected:
            return
        asset_id = selected[0]
        asset = self.get_asset_by_id(asset_id)
        if asset:
            self.review_note_var.set(asset.get("review_notes", ""))

    def get_asset_by_id(self, asset_id):
        for asset in self.assets:
            if asset["id"] == asset_id:
                return asset
        return None

    def approve_asset(self):
        if self.current_user["role"] != "admin":
            messagebox.showwarning("Permission denied", "Only admins can approve assets.")
            return

        selected = self.asset_tree.selection()
        if not selected:
            messagebox.showwarning("No asset selected", "Please select an asset to approve.")
            return

        asset_id = selected[0]
        notes = self.review_note_var.get().strip() or "Approved by administrator."
        update_asset_status(asset_id, "Approved", notes, self.current_user["user_id"])
        self.refresh_asset_list()
        messagebox.showinfo("Approved", "Asset has been approved.")

    def reject_asset(self):
        if self.current_user["role"] != "admin":
            messagebox.showwarning("Permission denied", "Only admins can reject assets.")
            return

        selected = self.asset_tree.selection()
        if not selected:
            messagebox.showwarning("No asset selected", "Please select an asset to reject.")
            return

        notes = self.review_note_var.get().strip()
        if not notes:
            messagebox.showwarning("Missing reason", "Please add a rejection reason before rejecting the asset.")
            return

        asset_id = selected[0]
        update_asset_status(asset_id, "Rejected", notes, self.current_user["user_id"])
        self.refresh_asset_list()
        messagebox.showinfo("Rejected", "Asset has been rejected.")

    def refresh_asset_list(self):
        self.assets = load_assets_for_user(self.current_user["email"], self.current_user["role"])

        for row in self.asset_tree.get_children():
            self.asset_tree.delete(row)

        display_assets = self.assets
        if self.current_filter != "All":
            display_assets = [asset for asset in self.assets if asset.get("status") == self.current_filter]

        for asset in display_assets:
            self.asset_tree.insert(
                "",
                "end",
                iid=asset["id"],
                values=(
                    asset["id"],
                    asset["title"],
                    asset["category"],
                    asset["uploader_name"],
                    asset["status"],
                    asset["file_name"],
                ),
            )

    def selected_asset_id(self):
        selected = self.asset_tree.selection()
        return selected[0] if selected else None

    def show_review_history(self):
        asset_id = self.selected_asset_id()
        if not asset_id:
            messagebox.showwarning("No asset selected", "Select an asset to see its review history.")
            return
        reviews = APP_STORE.list_reviews(asset_id)
        if not reviews:
            messagebox.showinfo("Review History", "No reviews have been recorded for this asset.")
            return
        lines = [
            f"{review['review_date']} | {review['decision']} | {review['comments'] or 'No comments'}"
            for review in reviews
        ]
        messagebox.showinfo("Review History", "\n".join(lines))

    def show_asset_details(self):
        asset_id = self.selected_asset_id()
        asset = self.get_asset_by_id(asset_id) if asset_id else None
        if not asset:
            messagebox.showwarning("No asset selected", "Select an asset to see its details.")
            return
        details = (
            f"Asset ID: {asset['asset_id']}\n"
            f"Name: {asset['asset_name']}\n"
            f"Description: {asset.get('description') or 'None'}\n"
            f"Category: {asset['category']}\n"
            f"File path: {asset['file_path']}\n"
            f"Uploaded by: {asset.get('uploaded_by_name', asset['uploaded_by'])}\n"
            f"Upload date: {asset['upload_date']}\n"
            f"Status: {asset['status']}"
        )
        messagebox.showinfo("Asset Details", details)

    def show_usage_rights(self):
        asset_id = self.selected_asset_id()
        if not asset_id:
            messagebox.showwarning("No asset selected", "Select an asset to see its usage rights.")
            return
        rights = APP_STORE.list_usage_rights(asset_id)
        if not rights:
            messagebox.showinfo("Usage Rights", "No usage rights have been recorded for this asset.")
            return
        lines = [
            f"Approved for: {right['approved_for']}\nExpires: {right['expiration_date'] or 'No expiry'}\nRestrictions: {right['restrictions'] or 'None'}"
            for right in rights
        ]
        messagebox.showinfo("Usage Rights", "\n\n".join(lines))

    def logout(self):
        self.destroy()
        LoginApp().mainloop()


if __name__ == "__main__":
    LoginApp().mainloop()
