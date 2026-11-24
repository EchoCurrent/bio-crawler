#!/usr/bin/env python3
"""
飞书应用机器人连接助手

用法:
  1. 验证凭证并列出机器人所在群聊(拿 chat_id):
     python scripts/feishu_setup.py --app-id cli_xxx --app-secret xxx --list-chats

  2. 发送测试消息:
     python scripts/feishu_setup.py --app-id cli_xxx --app-secret xxx --chat-id oc_xxx --send-test "连接测试"

  3. 不带 --app-id/--app-secret 时, 自动读取 config/sources.yaml 的 feishu.app 段。

需要应用权限: im:message (发消息), im:chat:readonly (列群聊), 且权限变更后需发布版本生效。
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path

import httpx
import yaml

BASE = "https://open.feishu.cn/open-apis"
PROJECT_ROOT = Path(__file__).resolve().parent.parent


async def get_tenant_token(client: httpx.AsyncClient, app_id: str, app_secret: str) -> str:
    r = await client.post(
        f"{BASE}/auth/v3/tenant_access_token/internal",
        json={"app_id": app_id, "app_secret": app_secret},
    )
    d = r.json()
    if d.get("code") != 0:
        sys.exit(
            f"获取 tenant_access_token 失败: code={d.get('code')} msg={d.get('msg')}\n"
            "  排查: 1) app_id/app_secret 是否正确  2) 应用是否已发布可用版本"
        )
    return d["tenant_access_token"]


async def list_chats(client: httpx.AsyncClient, token: str):
    chats, page_token = [], None
    while True:
        params = {"page_size": 100}
        if page_token:
            params["page_token"] = page_token
        r = await client.get(
            f"{BASE}/im/v1/chats",
            params=params,
            headers={"Authorization": f"Bearer {token}"},
        )
        d = r.json()
        if d.get("code") != 0:
            sys.exit(
                f"获取群列表失败: code={d.get('code')} msg={d.get('msg')}\n"
                "  排查: 需要 im:chat:readonly 权限, 且权限变更后已发布版本"
            )
        data = d.get("data", {})
        chats.extend(data.get("items", []))
        if not data.get("has_more"):
            break
        page_token = data.get("page_token")
    return chats


async def send_text(client: httpx.AsyncClient, token: str, chat_id: str, text: str):
    r = await client.post(
        f"{BASE}/im/v1/messages?receive_id_type=chat_id",
        json={
            "receive_id": chat_id,
            "msg_type": "text",
            "content": json.dumps({"text": text}),
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    return r.json()


def load_credentials(args):
    app_id, app_secret = args.app_id, args.app_secret
    if not (app_id and app_secret):
        from src.config_loader import load_config
        app = (load_config().get("feishu") or {}).get("app") or {}
        app_id = app_id or app.get("app_id")
        app_secret = app_secret or app.get("app_secret")
    if not app_id or not app_secret:
        sys.exit("缺少 app_id/app_secret: 请用 --app-id/--app-secret 传入, 或填入本地 config/secrets.yaml 的 feishu.app 段")
    if app_id.startswith("cli_xxxxxx") or app_secret.startswith("xxxxxx"):
        sys.exit("当前读到的是占位符配置, 请先填入真实的 app_id/app_secret (本地 config/secrets.yaml)")
    return app_id, app_secret


async def main():
    p = argparse.ArgumentParser(description="飞书应用机器人连接助手")
    p.add_argument("--app-id", help="应用 App ID (cli_ 开头), 不传则读 config/sources.yaml")
    p.add_argument("--app-secret", help="应用 App Secret, 不传则读 config/sources.yaml")
    p.add_argument("--list-chats", action="store_true", help="列出机器人所在群聊 (获取 chat_id)")
    p.add_argument("--chat-id", help="目标群聊 chat_id (oc_ 开头)")
    p.add_argument("--send-test", metavar="TEXT", help="向 --chat-id 发送测试文本消息")
    args = p.parse_args()

    app_id, app_secret = load_credentials(args)

    async with httpx.AsyncClient(timeout=30.0) as client:
        token = await get_tenant_token(client, app_id, app_secret)
        print(f"[OK] 凭证有效, 已获取 tenant_access_token (app_id={app_id})")

        if args.list_chats:
            chats = await list_chats(client, token)
            if not chats:
                print("[提示] 机器人不在任何群聊中。请先在飞书群里: 群设置 -> 群机器人 -> 添加此应用")
            else:
                print(f"[OK] 机器人所在群聊 ({len(chats)} 个):")
                for c in chats:
                    print(f"  chat_id={c.get('chat_id')}  群名={c.get('name')!r}")

        if args.send_test:
            if not args.chat_id:
                sys.exit("--send-test 需要同时指定 --chat-id")
            d = await send_text(client, token, args.chat_id, args.send_test)
            if d.get("code") == 0:
                print(f"[OK] 测试消息已发送到 {args.chat_id}")
            else:
                print(f"[失败] code={d.get('code')} msg={d.get('msg')}")
                print("  排查: 1) 机器人是否在目标群内  2) 是否有 im:message 权限并已发布版本")
                sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
