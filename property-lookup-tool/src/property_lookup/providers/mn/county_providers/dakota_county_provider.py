"""Reserved adapter for future Dakota County open-data enrichment."""


class DakotaCountyProvider:
    implemented = False

    def lookup_property(self, address: str):
        raise NotImplementedError("Dakota County enrichment is not implemented yet.")
