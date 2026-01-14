FROM fedora:40

RUN dnf -y update && \
    dnf -y install \
      python3 \
      python3-pip \
      ca-certificates \
      tzdata \
    && dnf clean all

WORKDIR /opt/yttrans

COPY install/requirements.txt /opt/yttrans/install/requirements.txt
RUN pip3 install --no-cache-dir -r /opt/yttrans/install/requirements.txt

COPY . /opt/yttrans

ENV PYTHONUNBUFFERED=1 \
    YTTRANS_HOST=0.0.0.0 \
    YTTRANS_PORT=9095

EXPOSE 9095

CMD ["python3", "/opt/yttrans/main.py", "--host", "0.0.0.0", "--port", "9095"]