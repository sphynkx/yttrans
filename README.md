[yttrans](https://github.com/sphynkx/yttrans) is supplemental service for [yurtube app](https://github.com/sphynkx/yurtube), based on gRPC+protobuf. It generates translations of captions on many different languages.

Currently service supports next translation services and models:
* __Google__ __Translate__ web-service (default) - simplest variant without any hardware requirements, useful for initial tests only.
* __M2M100__ __418M__ lang model from Facebook (~100 langs, [huggingface page](https://huggingface.co/facebook/m2m100_418M))
* __NLLB-200__ lang model from Facebook (~200 langs, [huggingface page](https://huggingface.co/facebook/nllb-200-distilled-600M))
* __MADLAB-400__ lang models from google (455 langs, [madlad400-10b-mt](https://huggingface.co/google/madlad400-10b-mt), [madlad400-3b-mt](https://huggingface.co/google/madlad400-3b-mt))
Best quality has __NLLB-200__ model..


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
Optionally - configure `.env` with your options, for example:
```conf
## This IP will send as service IP
YTTRANS_HOST=192.168.7.20
YTTRANS_PORT=9095

## IP of yurtube app, or 127.0.0.1,  or 0.0.0.0 for any
YTTRANS_BIND_HOST=0.0.0.0
YTTRANS_BIND_PORT=9095

# Optional auth. If empty - auth disabled.
AUTH_TOKEN=XXXXXXXXX

LOG_LEVEL=info

BUILD_HASH=dev
BUILD_TIME=2026-01-01T00:00:00Z


## Langs amount to handle simultaneously
JOB_LANG_PARALLELISM=4


## Switch bettween providers, working with different translation models/services (default is `googleweb`)
#YTTRANS_ENGINE=googleweb
#YTTRANS_ENGINE=fbm2m100
YTTRANS_ENGINE=fbnllb200d600m


# YTTRANS_LANGS=en,ru,uk,de # Force limit lang list. All langs if empty.
YTTRANS_LANGS=""
YTTRANS_TIMEOUT_SEC=60
YTTRANS_MAX_PARALLEL=2
YTTRANS_QUEUE_REDIS_URL=redis://localhost:6379/0
YTTRANS_MAXTOTALCHARS=4000



## Translation providers

# Params for googleweb provider
GOOGLEWEB_ORDER=googletrans,deep
GOOGLEWEB_QPS=2
GOOGLEWEB_TIMEOUT_SEC=10
GOOGLEWEB_RETRY_ATTEMPTS=3
GOOGLEWEB_RETRY_BACKOFF_SEC=30
GOOGLEWEB_MAX_CONCURRENCY=1


# Params for fbm2m100 provider
FBM2M100_MODEL=facebook/m2m100_418M
FBM2M100_DEVICE=cpu
FBM2M100_NUM_BEAMS=1
FBM2M100_MAX_NEW_TOKENS=128
# FBM2M100_TORCH_THREADS=4
FBM2M100_WARMUP=1
FBM2M100_MAX_INPUT_TOKENS=1024
FBM2M100_BATCH_SIZE=8
FBM2M100_MAX_CONCURRENCY=1


# Params for fbnllb200d600m provider
FBNLLB200D600M_WARMUP=1
FBNLLB200D600M_BATCH_SIZE=8
FBNLLB200D600M_NUM_BEAMS=1
FBNLLB200D600M_MAX_NEW_TOKENS=128
FBNLLB200D600M_MAX_INPUT_TOKENS=1024
# FBNLLB200D600M_TORCH_THREADS=4
FBNLLB200D600M_MAX_CONCURRENCY=1


# Params for madlad400 provider
MADLAD400_MODEL=google/madlad400-10b-mt
##MADLAD400_MODEL=google/madlad400-3b-mt
MADLAD400_DEVICE=cuda:0
##MADLAD400_DEVICE=cpu
MADLAD400_MAX_CONCURRENCY=1
MADLAD400_BATCH_SIZE=1
MADLAD400_MAX_INPUT_TOKENS=512
MADLAD400_MAX_NEW_TOKENS=256
MADLAD400_NUM_BEAMS=1
```

Install Redis:
```bash
dnf -y install redis
systemctl enable --now redis
```

Make sure that proto-file `proto/yttrans.proto` is same as in `yutrube` installation. If changes are made - it need to regenerate by commands:
```bash
cd proto
./gen_proto.sh
cd ..
```


### Manual run
Run service manually first time to initiate downloading of big model files:
```bash
cd /opt/yttrans
./run.sh
```


### Systemd Service
Configure and run as systemd service.
```bash
cp install/yttrans.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now yttrans
journalctl -u yttrans -f
```


### Docker install
Make sure that you have `/opt/yttrans/.env`. Otherwise copy it from `/opt/yttrans/install/.env.example`. Then:
```bash
cd /opt/yttrans/install/docker
docker-compose up -d --build
```
In case of configuring with `fbm2m100` provider recommended to send translation task:
```bash
grpcurl -plaintext 127.0.0.1:9095 yttrans.v1.Translator/ListLanguages
grpcurl -plaintext -d '{"video_id":"XXXXXXXXXXXX","src_vtt":"WEBVTT\n\n00:00:00.000 --> 00:00:02.000\nHello\n","src_lang":"en","target_langs":["ru","de","es","bg"]}' 127.0.0.1:9095 yttrans.v1.Translator/SubmitTranslate
```
This command initiates download of big model files and load model into memory.


### Google Web provider
Provider `googleweb` uses [Google Translate](https://translate.google.com/) service. Configured as default. Supports about 100 langs but may break on big texts and many requests. Recommended for test purposes only.


### Configure provider with M2M100 model
Provider `fbm2m100` works with model `M2M100 418M` from Facebook. This model supports about 100 langs. See details on its [huggingface page](https://huggingface.co/facebook/m2m100_418M).

In `.env` set appropriate provider to `YTTRANS_ENGINE` and add specific params:
```conf
YTTRANS_ENGINE=fbm2m100

# Params for fbm2m100 provider
FBM2M100_MODEL=facebook/m2m100_418M
FBM2M100_DEVICE=cpu
FBM2M100_NUM_BEAMS=1
FBM2M100_MAX_NEW_TOKENS=128
# FBM2M100_TORCH_THREADS=4
FBM2M100_WARMUP=1
FBM2M100_MAX_INPUT_TOKENS=1024
FBM2M100_BATCH_SIZE=8
FBM2M100_MAX_CONCURRENCY=1
```
To parallel handle several langs - edit `FBM2M100_MAX_CONCURRENCY`.

Restart service or docker container:
```bash
docker-compose restart yttrans
```
or, in case of `.env` modifications:
```bash
docker-compose up -d --force-recreate yttrans
```
Check list of available languages and engine name:
```bash
grpcurl -plaintext 127.0.0.1:9095 yttrans.v1.Translator/ListLanguages
```
It is recommended to run this command - it will help the model fit into memory faster.


### Configure provider with NLLB-200 model
Provider `fbnllb200d600m` supports translation using __NLLB-200__ __distilled__ __600M__ model from Facebook. Details about model see on its [huggingface page](https://huggingface.co/facebook/nllb-200-distilled-600M). Model supports about 200 languages. Configuration is analogical. In `.env` set appropriate provider to `YTTRANS_ENGINE` and add specific params:
```conf
YTTRANS_ENGINE=fbm2m100

# Params for fbnllb200d600m provider
FBNLLB200D600M_WARMUP=1
FBNLLB200D600M_BATCH_SIZE=8
FBNLLB200D600M_NUM_BEAMS=1
FBNLLB200D600M_MAX_NEW_TOKENS=128
FBNLLB200D600M_MAX_INPUT_TOKENS=1024
# FBNLLB200D600M_TORCH_THREADS=4
FBNLLB200D600M_MAX_CONCURRENCY=1
```
To parallel handle several langs - edit `FBNLLB200D600M_MAX_CONCURRENCY`.

Restart service or docker container:
```bash
docker-compose restart yttrans
```
or, in case of `.env` modifications:
```bash
docker-compose up -d --force-recreate yttrans
```
Check list of available languages and engine name:
```bash
grpcurl -plaintext 127.0.0.1:9095 yttrans.v1.Translator/ListLanguages
```
It is recommended to run this command - it will help the model fit into memory faster.


### Configure provider with MADLAD-400 models
Provider `madlad400` supports translation using __MADLAD-400__ __10B__ __MT__ or __MADLAD-400__ __3B__ __MT__ models from Facebook. Details about model see on its huggingface pages: [MADLAD-400 10B MT](https://huggingface.co/google/madlad400-10b-mt), [MADLAD-400 3B MT](https://huggingface.co/google/madlad400-3b-mt). Model supports 455 languages, but has worsk quality then previous model. Configuration is analogical. In `.env` set appropriate provider to `YTTRANS_ENGINE`, choose one of model variants and add specific params:
```conf
YTTRANS_ENGINE=madlad400

# Params for madlad400 provider
MADLAD400_MODEL=google/madlad400-10b-mt
##MADLAD400_MODEL=google/madlad400-3b-mt
MADLAD400_DEVICE=cuda:0
##MADLAD400_DEVICE=cpu
MADLAD400_MAX_CONCURRENCY=1
MADLAD400_BATCH_SIZE=1
MADLAD400_MAX_INPUT_TOKENS=512
MADLAD400_MAX_NEW_TOKENS=256
MADLAD400_NUM_BEAMS=1
```
To parallel handle several langs - edit `MADLAD400_MAX_CONCURRENCY`.

Restart service or docker container:
```bash
docker-compose restart yttrans
```
or, in case of `.env` modifications:
```bash
docker-compose up -d --force-recreate yttrans
```
Check list of available languages and engine name:
```bash
grpcurl -plaintext 127.0.0.1:9095 yttrans.v1.Translator/ListLanguages
```
It is recommended to run this command - it will help the model fit into memory faster.


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