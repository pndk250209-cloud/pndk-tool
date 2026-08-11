# account_manager.py
import json
import os
import time
import hashlib
from datetime import datetime

class AccountManager:
    def __init__(self, data_file="accounts.json"):
        self.data_file = data_file
        self.accounts = []
        self.current_account = None
        self.load_accounts()

    def load_accounts(self):
        try:
            if os.path.exists(self.data_file):
                with open(self.data_file, 'r', encoding='utf-8') as f:
                    self.accounts = json.load(f)
            else:
                self.accounts = []
                self.save_accounts()
        except:
            self.accounts = []

    def save_accounts(self):
        with open(self.data_file, 'w', encoding='utf-8') as f:
            json.dump(self.accounts, f, indent=2, ensure_ascii=False)

    def add_account(self, name, cookies, imei, note=""):
        account_id = hashlib.md5(f"{name}_{int(time.time())}".encode()).hexdigest()[:8]
        for acc in self.accounts:
            if acc.get("name") == name:
                return False, f"Tên '{name}' đã tồn tại!"
        account = {
            "id": account_id, "name": name, "cookies": cookies, "imei": imei,
            "note": note, "created_at": datetime.now().isoformat(),
            "last_used": None, "status": "active", "login_success": False, "box_count": 0
        }
        self.accounts.append(account)
        self.save_accounts()
        return True, account_id

    def get_account(self, account_id):
        for acc in self.accounts:
            if acc.get("id") == account_id:
                return acc
        return None

    def update_account(self, account_id, **kwargs):
        for acc in self.accounts:
            if acc.get("id") == account_id:
                for k, v in kwargs.items():
                    acc[k] = v
                acc["last_used"] = datetime.now().isoformat()
                self.save_accounts()
                return True
        return False

    def delete_account(self, account_id):
        for i, acc in enumerate(self.accounts):
            if acc.get("id") == account_id:
                del self.accounts[i]
                self.save_accounts()
                return True
        return False

    def set_current_account(self, account_id):
        acc = self.get_account(account_id)
        if acc:
            self.current_account = acc
            return True
        return False

    def get_current_account(self):
        return self.current_account

    def list_accounts(self):
        return self.accounts

    def get_active_accounts(self):
        return [acc for acc in self.accounts if acc.get("status") == "active"]

    def update_login_status(self, account_id, success, box_count=0):
        return self.update_account(account_id, login_success=success, box_count=box_count)