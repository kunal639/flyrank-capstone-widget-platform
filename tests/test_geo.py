from app.geo import GeoEnricher


class FailingProvider:
    def lookup(self, ip_address):
        raise TimeoutError("provider unavailable")


class StaticProvider:
    def __init__(self, data):
        self.data = data
        self.calls = 0

    def lookup(self, ip_address):
        self.calls += 1
        return self.data


def test_geo_enricher_falls_back_when_primary_fails():
    fallback = StaticProvider(
        {
            "country": "India",
            "city": "Patna",
            "region": "Bihar",
            "latitude": 25.5941,
            "longitude": 85.1376,
        }
    )
    enricher = GeoEnricher((FailingProvider(), fallback))

    assert enricher.enrich("8.8.8.8") == {
        "country": "India",
        "city": "Patna",
        "region": "Bihar",
        "latitude": 25.5941,
        "longitude": 85.1376,
    }
    assert fallback.calls == 1


def test_geo_enricher_returns_empty_data_when_all_providers_fail():
    assert GeoEnricher((FailingProvider(), FailingProvider())).enrich("8.8.8.8") == {}


def test_geo_enricher_skips_non_global_addresses():
    provider = StaticProvider({"country": "India"})

    assert GeoEnricher((provider,)).enrich("127.0.0.1") == {}
    assert provider.calls == 0
