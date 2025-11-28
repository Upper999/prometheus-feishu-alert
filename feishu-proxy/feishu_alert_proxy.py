# -*- coding: utf-8 -*-
# 文件名: feishu_alert_proxy.py
# 功能：接收 Alertmanager webhook → 转成飞书高级消息卡片（支持多告警、恢复、颜色、跳转链接）

from flask import Flask, request, jsonify
import requests
import json
from datetime import datetime

app = Flask(__name__)

# ←←←←←←←←←←←←←←←←←←←←←←←←←←←←←←←←←←
# 把这里改成你自己的飞书机器人 webhook 地址，不然无法向飞书发送告警信息。
FEISHU_WEBHOOK = "https://open.feishu.cn/open-apis/bot/v2/hook/xxxxxx"
# ←←←←←←←←←←←←←←←←←←←←←←←←←←←←←←←←←←

def build_feishu_card(alerts_data):
    """
    根据 Alertmanager 发来的数据生成飞书交互式卡片
    """
    # 统计 firing 和 resolved 数量
    firing_count = len([a for a in alerts_data["alerts"] if a["status"] == "firing"])
    resolved_count = len([a for a in alerts_data["alerts"] if a["status"] == "resolved"])

    # 根据状态决定卡片颜色和标题
    if resolved_count > 0 and firing_count == 0:
        header_color = "green"
        header_title = "告警已恢复"
    elif firing_count > 0:
        header_color = "red"
        header_title = f"告警触发 ({firing_count}个)"
    else:
        header_color = "grey"
        header_title = "告警通知"

    elements = []

    # 遍历每一条告警
    for alert in alerts_data["alerts"]:
        labels = alert.get("labels", {})
        annotations = alert.get("annotations", {})
        starts_at = alert.get("startsAt", "")
        ends_at = alert.get("endsAt", "")

        # 时间处理（转成北京时间）
        try:
            start_time = datetime.fromisoformat(starts_at.replace("Z", "+00:00")).astimezone(
                datetime.strptime("Asia/Shanghai", "%Z%z").tzinfo
            ).strftime("%Y-%m-%d %H:%M:%S")
        except:
            start_time = starts_at

        status_emoji = "已恢复" if alert["status"] == "resolved" else "告警中"

        # 单条告警卡片内容
        elements.append({
            "tag": "div",
            "text": {
                "tag": "lark_md",
                "content": f"**{status_emoji} {labels.get('alertname', '未知告警')}**"
            }
        })

        # 详细信息
        fields = [
            f"**实例**：{labels.get('instance', 'N/A')}",
            f"**级别**：{labels.get('severity', 'info')}",
            f"**触发时间**：{start_time}",
        ]
        if annotations.get("summary"):
            fields.append(f"**概要**：{annotations['summary']}")
        if annotations.get("description"):
            fields.append(f"**详情**：{annotations['description']}")

        elements.append({
            "tag": "div",
            "text": {
                "tag": "lark_md",
                "content": "\n".join(fields)
            }
        })

        # 查看 Prometheus 链接（方便点进去看图）
        generator_url = alert.get("generatorURL", "")
        if generator_url:
            elements.append({
                "tag": "action",
                "actions": [{
                    "tag": "button",
                    "text": {"tag": "plain_text", "content": "查看图表"},
                    "type": "primary",
                    "url": generator_url
                }]
            })

        # 分隔线
        elements.append({"tag": "hr"})

    # 去掉最后一个多余的分隔线
    if elements and elements[-1].get("tag") == "hr":
        elements.pop()

    # 卡片整体结构
    card = {
        "msg_type": "interactive",
        "card": {
            "config": {"wide_screen_mode": True},
            "header": {
                "title": {"tag": "plain_text", "content": header_title},
                "template": header_color
            },
            "elements": elements
        }
    }

    return json.dumps(card, ensure_ascii=False)


@app.route('/alert', methods=['POST'])
def alert_webhook():
    """
    Alertmanager 调用此接口
    """
    if not request.is_json:
        return jsonify({"error": "Content-Type must be application/json"}), 400

    data = request.get_json()
    if not data:
        return jsonify({"error": "empty payload"}), 400

    # 打印原始数据方便调试
    print("收到 Alertmanager 数据:", json.dumps(data, ensure_ascii=False, indent=2))

    # 构建飞书卡片
    feishu_payload = build_feishu_card(data)

    # 发送到飞书
    try:
        resp = requests.post(
            FEISHU_WEBHOOK,
            headers={"Content-Type": "application/json"},
            data=feishu_payload.encode("utf-8"),
            timeout=10
        )
        resp.raise_for_status()
        print(f"飞书发送成功，状态码：{resp.status_code}")
    except Exception as e:
        print(f"飞书发送失败: {e}")
        return jsonify({"error": str(e)}), 500

    return jsonify({"status": "ok"}), 200


@app.route('/health', methods=['GET'])
def health():
    return "OK", 200


if __name__ == '__main__':
    print("飞书告警中转站启动成功 → http://0.0.0.0:4000/alert")
    app.run(host='0.0.0.0', port=4000, debug=False)
