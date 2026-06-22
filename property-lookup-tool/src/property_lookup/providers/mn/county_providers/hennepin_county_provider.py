"""Reserved adapter for future Hennepin County open-data enrichment."""


class HennepinCountyProvider:
    implemented = False

    def lookup_property(self, address: str):
        raise NotImplementedError("Hennepin County enrichment is not implemented yet.")
