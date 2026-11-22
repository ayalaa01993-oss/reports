
import random
import statistics


class HoursModel:
    """Learns entry time and shift length and samples new pairs."""

    MIN_STD_ENTRY = 10
    MIN_STD_LENGTH = 20
    CLIP = 2.5

    def fit(self, entries: list[int], lengths: list[int]) -> None:
        self.mean_e = statistics.fmean(entries)
        self.mean_l = statistics.fmean(lengths)

        self.std_e = max(
            statistics.pstdev(entries),
            self.MIN_STD_ENTRY
        )

        self.std_l = max(
            statistics.pstdev(lengths),
            self.MIN_STD_LENGTH
        )

        try:
            corr = statistics.correlation(entries, lengths)
            self.corr = max(-0.9, min(0.9, corr))
        except statistics.StatisticsError:
            self.corr = 0.0

    def sample(
        self,
        rng: random.Random,
        min_length: int = 60
    ) -> tuple[int, int]:

        clip = lambda z: max(-self.CLIP, min(self.CLIP, z))

        z1, z2 = rng.gauss(0, 1), rng.gauss(0, 1)

        entry = round(self.mean_e + self.std_e * clip(z1))

        z_len = clip(
            self.corr * z1 +
            (1 - self.corr ** 2) ** 0.5 * z2
        )

        length = max(
            round(self.mean_l + self.std_l * z_len),
            min_length
        )

        entry = min(entry, 24 * 60 - 1 - length)

        return entry, length
