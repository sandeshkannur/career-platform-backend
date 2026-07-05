FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
# - libpango/libharfbuzz: required by WeasyPrint (PDF report rendering)
# - fontconfig + fonts-noto-core: Noto Sans + Noto Sans Kannada so kn-IN
#   reports render real glyphs instead of tofu boxes
# - fonts-dejavu-core: fallback for symbol glyphs (★ fit-band stars)
RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    curl \
    libpango-1.0-0 \
    libpangoft2-1.0-0 \
    libharfbuzz0b \
    libharfbuzz-subset0 \
    fontconfig \
    fonts-noto-core \
    fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first (better caching)
COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

# Copy entire backend code
COPY . .

# Expose FastAPI port
EXPOSE 8000

# Use existing entrypoint
CMD ["sh", "entrypoint.sh"]
