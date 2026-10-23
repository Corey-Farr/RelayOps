FROM python:3.13.9-slim
WORKDIR /app
RUN useradd --uid 10001 --create-home sink && mkdir /data && chown sink:sink /data
COPY server.py .
USER sink
EXPOSE 8081
HEALTHCHECK --interval=10s --timeout=3s --retries=5 CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8081/health', timeout=2)"
CMD ["python", "-u", "server.py"]
