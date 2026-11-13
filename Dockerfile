FROM python:3.12-slim-bookworm@sha256:935c3c5b12357a7e10caa9c1e6ca5692344d97cf229832ef584be2cec9fc03df
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
ENV HOME=/home/x2 USER=x2 LOGNAME=x2
WORKDIR /app
COPY x2_motion/requirements-dashboard.txt /app/x2_motion/requirements-dashboard.txt
RUN pip install --no-cache-dir -r /app/x2_motion/requirements-dashboard.txt && useradd --system --uid 10001 --create-home x2 && mkdir -p /data && chown x2 /data
COPY x2_motion /app/x2_motion
COPY docker /app/docker
EXPOSE 8766
ENTRYPOINT ["python", "/app/docker/entrypoint.py"]
CMD ["serve"]
