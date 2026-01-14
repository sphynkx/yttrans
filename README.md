[yttrans](https://github.com/sphynkx/yttrans) is supplemental service for [yurtube app](https://github.com/sphynkx/yurtube), based on gRPC+protobuf. It generates translations of captions on many different languages.

Currently service support Google Translate service but may be expand with other translation providers or with custom models.


## Install and configure.
Download service from repository and install:
```bash
cd /opt
git clone https://github.com/sphynkx/yttrans
cd yttrans
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r install/requirements.txt
deactivate
cp install/.env.example .env
```
Optionally - configure `.env` with your options.

Install Redis:
```bash
dnf -y install redis
```

Make sure that proto-file `proto/yttrans.proto` is same as in `yutrube` installation. If changes are made - it need to regenerate by commands:
```bash
cd proto
./gen_proto.sh
cd ..
```

Configure and run as systemd service.
```bash
cp install/yttrans.service /etc/systemd/system/
systemctl enable --now yttrans
journalctl -u yttrans -f
```

## Test and usage
Health check/show methods via reflections:
```bash
dnf -y install grpcurl
grpcurl -plaintext 127.0.0.1:9095 list
grpcurl -plaintext 127.0.0.1:9095 describe yttrans.v1.Translator
```

Descriptions:
```bash
grpcurl -plaintext 127.0.0.1:9095 describe yttrans.v1.Translator
grpcurl -plaintext 127.0.0.1:9095 describe grpc.health.v1.Info
```

List of available languages:
```bash
grpcurl -plaintext 127.0.0.1:9095 yttrans.v1.Translator/ListLanguages
```

Manual request and receive `JOB_ID`:
```bash
grpcurl -plaintext -d '{"video_id":"RsnV6dlw1nR8","src_vtt":"WEBVTT\n\n00:00:00.000 --> 00:00:02.000\nHello\n","src_lang":"en","target_langs":["ru","de"],"options":{"engine":"google"}}' 127.0.0.1:9095 yttrans.v1.Translator/SubmitTranslate
```

Get request status:
```bash
grpcurl -plaintext -d '{"job_id":"<JOB_ID>"}' 127.0.0.1:9095 yttrans.v1.Translator/GetStatus
```

Get translated result:
```bash
grpcurl -plaintext -d '{"job_id":"<JOB_ID>"}' 127.0.0.1:9095 yttrans.v1.Translator/GetResult
```