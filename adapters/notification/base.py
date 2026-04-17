"""
Abstract base class that all notification adapters must implement.
Methods to implement: send_message(channel, message), send_alert(channel, message),
send_feedback_prompt(channel, issue_id), health_check().
To add a new notifier: subclass this class and implement all methods.
"""
