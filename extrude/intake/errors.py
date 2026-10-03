"""The card and the sentence disagree."""


class SpecRejected(ValueError):
    """A limit on the card is not in the sentence, or the hash does not match."""
