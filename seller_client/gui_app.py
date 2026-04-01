from __future__ import annotations

import json
import threading
import tkinter as tk
from pathlib import Path
from tkinter import ttk

from seller_client.agent_mcp import (
    configure_registry_trust,
    get_client_config,
    onboard_seller_from_intent,
    push_and_report_image,
)
from seller_client.installer import bootstrap_client


class SellerClientApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Seller Client MVP")
        self.root.geometry("980x760")

        self.state_dir = str(Path.cwd() / ".cache" / "seller-gui")

        self.email_var = tk.StringVar(value="seller-gui@example.com")
        self.password_var = tk.StringVar(value="super-secret-password")
        self.display_name_var = tk.StringVar(value="GUI Seller")
        self.backend_url_var = tk.StringVar(value="http://127.0.0.1:8000")
        self.intent_var = tk.StringVar(value="我能把自己电脑性能的10%上传到平台获取收益吗")

        self.registry_var = tk.StringVar(value="pivotcompute.store")
        self.local_image_var = tk.StringVar(value="alpine:3.20")
        self.repository_var = tk.StringVar(value="seller/gui-alpine")
        self.remote_tag_var = tk.StringVar(value="3.20")

        self._build()

    def _build(self) -> None:
        frame = ttk.Frame(self.root, padding=12)
        frame.pack(fill=tk.BOTH, expand=True)

        onboarding_form = ttk.LabelFrame(frame, text="卖家接入参数", padding=10)
        onboarding_form.pack(fill=tk.X)

        onboarding_rows = [
            ("邮箱", self.email_var, ""),
            ("密码", self.password_var, "*"),
            ("显示名", self.display_name_var, ""),
            ("后端地址", self.backend_url_var, ""),
            ("自然语言意图", self.intent_var, ""),
        ]
        for idx, (label, variable, show) in enumerate(onboarding_rows):
            ttk.Label(onboarding_form, text=label).grid(row=idx, column=0, sticky="w", pady=4)
            ttk.Entry(onboarding_form, textvariable=variable, width=90, show=show).grid(
                row=idx, column=1, sticky="ew", pady=4
            )
        onboarding_form.columnconfigure(1, weight=1)

        upload_form = ttk.LabelFrame(frame, text="镜像上传参数", padding=10)
        upload_form.pack(fill=tk.X, pady=(10, 0))

        upload_rows = [
            ("Registry", self.registry_var),
            ("本地镜像", self.local_image_var),
            ("仓库路径", self.repository_var),
            ("远程 Tag", self.remote_tag_var),
        ]
        for idx, (label, variable) in enumerate(upload_rows):
            ttk.Label(upload_form, text=label).grid(row=idx, column=0, sticky="w", pady=4)
            ttk.Entry(upload_form, textvariable=variable, width=90).grid(
                row=idx, column=1, sticky="ew", pady=4
            )
        upload_form.columnconfigure(1, weight=1)

        button_bar = ttk.Frame(frame, padding=(0, 10))
        button_bar.pack(fill=tk.X)

        ttk.Button(button_bar, text="安装器 Dry Run", command=self.run_installer).pack(side=tk.LEFT, padx=4)
        ttk.Button(button_bar, text="开始接入", command=self.run_onboarding).pack(side=tk.LEFT, padx=4)
        ttk.Button(button_bar, text="刷新本地配置", command=self.refresh_config).pack(side=tk.LEFT, padx=4)
        ttk.Button(button_bar, text="检查 Registry 连接", command=self.run_registry_trust).pack(side=tk.LEFT, padx=4)
        ttk.Button(button_bar, text="上传并上报镜像", command=self.run_push_image).pack(side=tk.LEFT, padx=4)

        self.log = tk.Text(frame, height=30, wrap="word")
        self.log.pack(fill=tk.BOTH, expand=True)

    def _append_log(self, title: str, payload: object) -> None:
        self.log.insert(tk.END, f"\n=== {title} ===\n")
        self.log.insert(tk.END, json.dumps(payload, ensure_ascii=False, indent=2))
        self.log.insert(tk.END, "\n")
        self.log.see(tk.END)

    def _run_in_thread(self, title: str, func) -> None:
        def target() -> None:
            try:
                result = func()
            except Exception as exc:  # noqa: BLE001
                result = {"ok": False, "error": str(exc)}
            self.root.after(0, lambda: self._append_log(title, result))

        threading.Thread(target=target, daemon=True).start()

    def run_installer(self) -> None:
        self._run_in_thread(
            "installer",
            lambda: bootstrap_client(dry_run=True, state_dir=self.state_dir),
        )

    def run_onboarding(self) -> None:
        self._run_in_thread(
            "onboarding",
            lambda: onboard_seller_from_intent(
                intent=self.intent_var.get(),
                email=self.email_var.get(),
                password=self.password_var.get(),
                display_name=self.display_name_var.get(),
                backend_url=self.backend_url_var.get(),
                state_dir=self.state_dir,
            ),
        )

    def refresh_config(self) -> None:
        self._run_in_thread(
            "config",
            lambda: get_client_config(state_dir=self.state_dir),
        )

    def run_registry_trust(self) -> None:
        self._run_in_thread(
            "registry_trust",
            lambda: configure_registry_trust(self.registry_var.get()),
        )

    def run_push_image(self) -> None:
        self._run_in_thread(
            "push_and_report_image",
            lambda: push_and_report_image(
                local_tag=self.local_image_var.get(),
                repository=self.repository_var.get(),
                remote_tag=self.remote_tag_var.get(),
                registry=self.registry_var.get(),
                backend_url=self.backend_url_var.get(),
                state_dir=self.state_dir,
            ),
        )


def main() -> None:
    root = tk.Tk()
    SellerClientApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
