"""本地快照到个人工作区的单向保存、审核续接及显式导入。"""

import base64
import json
from urllib.parse import urljoin, urlsplit
from urllib.request import urlopen

from .bundle import prepare_bundle
from .codex import Codex
from .quiz_rendering import collect_quiz_edge_image_references


def public_verification_methods():
    with urlopen(
        "https://goodwen.cc/api/public/verification-methods", timeout=15
    ) as response:
        items = json.load(response)["items"]
    methods = {item["id"] for item in items if item["enabled"]}
    methods &= {"phone", "email", "wechat", "google", "github"}
    if not methods:
        raise ValueError("Goodwen 当前没有可用的填写者验证方式")
    return sorted(methods)


def official(url):
    address = urljoin("https://goodwen.cc/", url)
    if urlsplit(address).netloc != "goodwen.cc" or urlsplit(address).scheme != "https":
        raise ValueError("Goodwen 返回的链接地址无效")
    return address


def workspace(client, lib, *, connect=False, permission="questionnaires:write"):
    workspaces = client.call("workspace_list")["workspaces"]
    matches = [w for w in workspaces if w["kind"] == "personal"]
    if len(matches) != 1:
        raise RuntimeError("当前授权需要一个可访问的 Goodwen 个人工作区")
    selected = matches[0]
    if permission not in selected["available_scopes"]:
        if permission == "results:import" and client.interactive:
            client.login()
            return workspace_after_import_login(client, selected)
        raise RuntimeError("个人工作区缺少权限 " + permission)
    current = lib.pref("workspace")
    if current != selected["workspace_id"]:
        if not connect:
            raise RuntimeError("当前授权与原个人工作区不同，请在 Skill 中重新连接")
        lib.set_pref("workspace", selected["workspace_id"])
    return selected["workspace_id"]


def workspace_after_import_login(client, selected):
    visible = client.call("workspace_list")["workspaces"]
    if not any(
        w["workspace_id"] == selected["workspace_id"]
        and w["kind"] == "personal"
        and "results:import" in w["available_scopes"]
        for w in visible
    ):
        raise RuntimeError("当前个人工作区未授权历史答卷导入")
    return selected["workspace_id"]


def transfer(client, lib, ws, snap):
    with lib.db(write=True) as db:
        survey = db.execute(
            "SELECT * FROM survey WHERE id=?", (snap["survey_id"],)
        ).fetchone()
        if survey["local_only"] or survey["owner"] not in (None, ws):
            raise ValueError("该问卷为仅本地或已绑定另一账号")
        db.execute(
            "UPDATE survey SET owner=? WHERE id=? AND owner IS NULL", (ws, survey["id"])
        )
        known = db.execute(
            "SELECT * FROM cloud_version WHERE workspace=? AND snapshot=?",
            (ws, snap["id"]),
        ).fetchone()
        previous = db.execute(
            "SELECT * FROM cloud_map WHERE workspace=? AND survey=?", (ws, survey["id"])
        ).fetchone()
    editing_latest = (
        survey["latest"] == snap["id"]
        and previous
        and previous["snapshot"] != snap["id"]
    )
    if known and (known["release"] or not editing_latest):
        draft = client.call(
            "questionnaire_draft_get", workspace_id=ws, draft_id=known["draft"]
        )["draft"]
        if draft["digest"] != known["digest"]:
            if known["release"]:
                return dict(known)
            raise RuntimeError("revision_conflict · 云端草稿已被修改，请审核差异")
    else:
        source, assets, digest = prepare_bundle(lib, snap)
        if previous and survey["latest"] != snap["id"]:
            raise ValueError("该本地历史版本尚未建立在线对应关系")
        fields = {
            "workspace_id": ws,
            "local_id": survey["id"],
            "snapshot_digest": digest,
        }
        if previous:
            fields.update(
                draft_id=previous["draft"], expected_digest=previous["digest"]
            )
        prepared = client.call(
            "questionnaire_local_sync",
            action="prepare",
            asset_hashes=sorted({r["hash"] for r in assets}),
            **fields,
        )
        current = prepared["draft"]
        if not prepared.get("complete"):
            edges = collect_quiz_edge_image_references(snap["spec"])
            needed = set(prepared["missing"])
            for asset in assets:
                if asset["hash"] not in needed:
                    continue
                with lib.db() as db:
                    blob = db.execute(
                        "SELECT content FROM blob WHERE hash=?", (asset["hash"],)
                    ).fetchone()[0]
                client.call(
                    "questionnaire_local_sync",
                    workspace_id=ws,
                    action="asset",
                    local_id=survey["id"],
                    snapshot_digest=digest,
                    draft_id=current["id"],
                    expected_digest=current["digest"],
                    filename=asset["path"].split("/")[-1],
                    mime=asset["mime"],
                    asset_hash=asset["hash"],
                    edge=asset["path"] in edges,
                    content_b64=base64.b64encode(blob).decode("ascii"),
                )
                needed.remove(asset["hash"])
            draft = client.call(
                "questionnaire_local_sync",
                workspace_id=ws,
                action="commit",
                local_id=survey["id"],
                snapshot_digest=digest,
                draft_id=current["id"],
                expected_digest=current["digest"],
                source_qml=source,
            )["draft"]
        else:
            draft = current
    release = draft.get("approved_release") or {}
    record = {
        "workspace": ws,
        "survey": survey["id"],
        "snapshot": snap["id"],
        "draft": draft["id"],
        "digest": draft["digest"],
        "review": official(draft["review_url"]),
        "pack": release.get("pack_id"),
        "release": release.get("id"),
    }
    with lib.db(write=True) as db:
        db.execute(
            "INSERT OR REPLACE INTO cloud_version VALUES(:workspace,:snapshot,:draft,:digest,:pack,:release)",
            record,
        )
        if not previous:
            db.execute(
                "INSERT OR IGNORE INTO cloud_map VALUES(:workspace,:survey,:snapshot,:draft,:digest,:review,:pack,:release)",
                record,
            )
        elif not known or not known["release"] or previous["snapshot"] == snap["id"]:
            db.execute(
                "UPDATE cloud_map SET snapshot=:snapshot,draft=:draft,digest=:digest,review=:review,"
                "pack=:pack,release=:release WHERE workspace=:workspace AND survey=:survey "
                "AND draft=:was_draft AND digest=:was_digest",
                {
                    **record,
                    "was_draft": previous["draft"],
                    "was_digest": previous["digest"],
                },
            )
    return record


def drain(client, lib, ws, skip=None):
    receipts = []
    for survey in lib.surveys():
        if (
            survey["latest"] == skip
            or survey["local_only"]
            or survey["owner"] not in (None, ws)
        ):
            continue
        try:
            receipts.append(transfer(client, lib, ws, lib.snapshot(survey["latest"])))
        except (RuntimeError, ValueError) as exc:
            receipts.append({"survey": survey["id"], "error": str(exc)})
    return receipts


def sync(lib, *, connect=False, only=None):
    if not connect and lib.pref("paused") == "yes":
        return {"status": "paused"}
    with Codex(interactive=connect) as client:
        ws = workspace(client, lib, connect=connect)
        if lib.pref("paused") == "yes":
            return {"workspace": ws, "status": "paused", "items": []}
        if only:
            return transfer(client, lib, ws, lib.snapshot(only))
        return {"workspace": ws, "items": drain(client, lib, ws)}


def publish(lib, snapshot, participant=None, on_login=None, verification_methods=None):
    snap = lib.snapshot(snapshot)
    with Codex(interactive=True, on_login=on_login) as client:
        ws = workspace(client, lib, connect=True)
        record = transfer(client, lib, ws, snap)
        if lib.pref("paused") != "yes":
            drain(client, lib, ws, skip=snapshot)
        if not record.get("release"):
            status, url = "review", record["review"]
        else:
            args = {
                "workspace_id": ws,
                "release_id": record["release"],
                "idempotency_key": f"local-{snapshot}-{record['release']}-{participant or 'public'}",
            }
            if participant:
                d = client.call(
                    "distribution_invitation_create", participant_id=participant, **args
                )
                url = official(d.get("share_url") or d["detail_url"])
            else:
                args["verification_methods"] = (
                    sorted(set(verification_methods))
                    if verification_methods
                    else public_verification_methods()
                )
                args["idempotency_key"] += "-" + "-".join(args["verification_methods"])
                d = client.call("distribution_public_link_create", **args)[
                    "distribution"
                ]
                url = official(d["share_url"])
            status = "published"
        with lib.db(write=True) as db:
            db.execute(
                "INSERT OR REPLACE INTO publication(snapshot,workspace,status,url) VALUES(?,?,?,?)",
                (snapshot, ws, status, url),
            )
        return {"status": status, "url": url, **record}


def mapped_release(client, lib, snapshot, ws):
    with lib.db() as db:
        row = db.execute(
            "SELECT * FROM cloud_version WHERE workspace=? AND snapshot=?",
            (ws, snapshot),
        ).fetchone()
    if not row:
        raise ValueError("请先将本地版本交给 Goodwen 并完成审核")
    if row["release"]:
        return dict(row)
    return transfer(client, lib, ws, lib.snapshot(snapshot))


def import_answers(lib, snapshot, count):
    rows = lib.responses(snapshot)
    if count is not None and count != len(rows):
        raise ValueError("本地答卷数量已变化，请重新确认")
    with Codex(interactive=count is not None, import_scope=count is not None) as client:
        ws = workspace(client, lib, permission="results:read")
        target = mapped_release(client, lib, snapshot, ws)
        if not target.get("release"):
            raise ValueError("请先审核此问卷版本")
        if count is None:
            return {
                "snapshot": snapshot,
                "workspace": ws,
                "release": target["release"],
                "count": len(rows),
                "requires_confirmation": True,
            }
        if not rows:
            return {"items": []}
        workspace(client, lib, permission="results:import")
        items = []
        for row in rows:
            receipt = client.call(
                "result_local_import",
                workspace_id=ws,
                release_id=target["release"],
                source_digest=target["digest"],
                submissions=[
                    {
                        "id": row["id"],
                        "language": row["language"],
                        "answers": row["answers"],
                        "timing": row["timing"],
                        "submitted_at": row["submitted"],
                    }
                ],
            )
            items.extend(receipt["items"])
        return {"items": items}


def online_results(lib, snapshot, source):
    with Codex() as client:
        ws = workspace(client, lib, permission="results:read")
        target = mapped_release(client, lib, snapshot, ws)
        if not target.get("release"):
            raise ValueError("此版本仍待审核")
        args = {"workspace_id": ws, "release_id": target["release"], "source": source}
        results = []
        cursor = None
        while True:
            page = client.call("questionnaire_response_list", **args, cursor=cursor)
            for row in page["items"]:
                result = client.call(
                    "questionnaire_response_get",
                    workspace_id=ws,
                    release_id=target["release"],
                    source=row["source"],
                    response_id=row["id"],
                )
                results.append(result["response"])
            cursor = page.get("next_cursor")
            if not cursor:
                return {
                    "count": len(results),
                    "counts": page["counts"],
                    "items": results,
                }
