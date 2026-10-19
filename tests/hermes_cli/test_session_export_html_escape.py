import re

from hermes_cli.session_export_html import _generate_messages_html


def test_rendered_export_brands_defaults_and_preserves_custom_session_content():
    from hermes_cli.session_export_html import generate_multi_session_html_export

    sessions = [{"id": "one", "messages": [{"role": "assistant", "content": "Hermes model response"}]},
                {"id": "two", "title": "Hermes custom title", "messages": []}]
    html = generate_multi_session_html_export(sessions)

    assert "<title>Loki Session Export</title>" in html
    assert "Loki History" in html and "<h1>Loki Session</h1>" in html
    assert "Built with ᛚ Loki" in html
    assert "Hermes custom title" in html and "Hermes model response" in html

def test_role_is_escaped_in_html_export():
    messages = [
        {
            "role": "<img src=x onerror=alert(document.domain)>",
            "content": "hello",
            "timestamp": 1700000000,
        }
    ]

    html = _generate_messages_html(messages)

    assert "<img src=x onerror=alert(document.domain)>" not in html
    assert "&lt;img src=x onerror=alert(document.domain)&gt;" in html
    # The class attribute must remain a single, well-formed token: a crafted
    # role must not break out of it nor split into several unintended classes.
    class_value = re.search(r'class="(message message-[^"]*active)"', html)
    assert class_value is not None
    assert " message-" in class_value.group(1)  # exactly one message-<role> class
    assert class_value.group(1).count("message-") == 1
