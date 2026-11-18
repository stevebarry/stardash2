# Gunicorn configuration for the BI Dashboard (foreground testing; the systemd unit binds a Unix socket instead)
bind = "127.0.0.1:8000"
workers = 3
threads = 2
timeout = 120          # long-running dashboard queries / exports
accesslog = "-"
errorlog = "-"
