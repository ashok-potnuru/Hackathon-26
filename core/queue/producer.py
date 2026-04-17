"""
Pushes a pipeline job to the queue (SQS or Redis) as soon as a webhook is received.
The webhook handler must return HTTP 200 immediately — never run pipeline logic here.
Implement job serialization and queue-client interaction in this module.
"""
