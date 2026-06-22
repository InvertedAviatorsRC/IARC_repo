"""Reserved adapter for future Washington County open-data enrichment."""


class WashingtonCountyProvider:
    implemented = False

    def lookup_property(self, address: str):
        raise NotImplementedError("Washington County enrichment is not implemented yet.")
