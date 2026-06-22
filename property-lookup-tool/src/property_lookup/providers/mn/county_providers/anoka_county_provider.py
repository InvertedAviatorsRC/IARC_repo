"""Reserved adapter for future Anoka County open-data enrichment."""


class AnokaCountyProvider:
    implemented = False

    def lookup_property(self, address: str):
        raise NotImplementedError("Anoka County enrichment is not implemented yet.")
