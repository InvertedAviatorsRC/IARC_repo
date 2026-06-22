"""Reserved adapter for future Ramsey County open-data enrichment."""


class RamseyCountyProvider:
    implemented = False

    def lookup_property(self, address: str):
        raise NotImplementedError("Ramsey County enrichment is not implemented yet.")
