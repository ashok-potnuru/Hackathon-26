"""
Abstract base class that all cloud provider adapters must implement.
Methods to implement: store_file(key, data), read_file(key), queue_job(payload),
get_secret(name), health_check().
To add a new cloud provider: subclass this class and implement all methods.
"""
