FROM python:3.12-slim

WORKDIR /app

# Install fonts (metric-compatible open-source substitutes)
# - fonts-liberation: Liberation Sans/Serif/Mono (Arial, Times New Roman, Courier New)
# - fonts-crosextra-carlito: Carlito (Calibri substitute)
# - fonts-crosextra-caladea: Caladea (Cambria substitute)
# - fonts-croscore: Arimo, Tinos, Cousine (Arial, Times, Courier alternates)
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        fonts-liberation \
        fonts-crosextra-carlito \
        fonts-crosextra-caladea \
        fonts-croscore \
        fontconfig \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Copy proprietary fonts if available (not committed to repo)
# Populate fonts/ from a licensed machine, e.g.:
#   cp /System/Library/Fonts/Supplemental/{Arial,Calibri,Cambria,Times\ New\ Roman,Courier\ New,Georgia,Verdana}.ttf fonts/
COPY fonts/ /usr/share/fonts/truetype/msfonts/
RUN fc-cache -f

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY unredact/ ./unredact/

# Run the API
ENV PORT=8080
EXPOSE 8080

CMD ["sh", "-c", "uvicorn unredact.api:app --host 0.0.0.0 --port ${PORT}"]
