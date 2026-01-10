import redis


def redis_client(redis_url):
    return redis.Redis.from_url(redis_url, decode_responses=True)