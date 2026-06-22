"""Reserved adapter for future Carver County open-data enrichment."""


class CarverCountyProvider:
    implemented = False

    def lookup_property(self, address: str):
        raise NotImplementedError("Carver County enrichment is not implemented yet.")
