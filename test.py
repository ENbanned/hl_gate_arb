from datetime import datetime, UTC

# Было
timestamp = datetime.utcnow()
print(timestamp)

# Стало  
timestamp = datetime.now(UTC)

print(timestamp)