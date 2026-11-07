import unittest

from mmv.prose_humanizer import humanize_direction, humanize_panels


class ProseHumanizerTests(unittest.TestCase):
    def test_strip_marker_t1_cliches(self):
        # Marker T1: "testament to"
        raw = "The ruined wall stands as a testament to the old war."
        self.assertEqual(humanize_direction(raw), "The ruined wall is evidence of the old war.")

        self.assertEqual(humanize_direction("The hall is a testament to decay."), "The hall is evidence of decay.")

        # Marker T1: "delve into"
        raw = "She delved into the dark tunnel with her lantern."
        self.assertEqual(humanize_direction(raw), "She entered the dark tunnel with her lantern.")

        # Marker T1: "tapestry of"
        raw = "The market was a rich tapestry of neon signs and steam."
        self.assertEqual(humanize_direction(raw), "The market was a mixture of neon signs and steam.")

        # Marker T1: "dance of light and shadow"
        raw = "A delicate dance of shadow and light across the wet pavement."
        self.assertEqual(humanize_direction(raw), "Stark light and deep shadows across the wet pavement.")

        # Marker T1: "palpable tension"
        raw = "There is palpable tension between the two guards."
        self.assertEqual(humanize_direction(raw), "There is heavy stillness between the two guards.")

        # Marker T1: "shivers down spine"
        raw = "A cold draft sends shivers down his spine."
        self.assertEqual(humanize_direction(raw), raw)

        # Marker T1: "unspoken understanding"
        raw = "They exchange an unspoken understanding before moving."
        self.assertEqual(humanize_direction(raw), "They exchange a shared glance before moving.")

    def test_strip_marker_t3_throat_clearing(self):
        raw = "In this shot, we see the protagonist climbing the ladder."
        self.assertEqual(humanize_direction(raw), "The protagonist climbing the ladder.")

        raw = "This panel depicts a dark alley with steam rising."
        self.assertEqual(humanize_direction(raw), "A dark alley with steam rising.")

        raw = "We can see headlights flashing through the trees."
        self.assertEqual(humanize_direction(raw), "Headlights flashing through the trees.")

    def test_strip_trailing_abstract_atmosphere(self):
        raw = "The car accelerates down the highway, creating a sense of urgency."
        self.assertEqual(humanize_direction(raw), "The car accelerates down the highway.")

        raw = "Rain lashes against the window, evoking an atmosphere of despair."
        self.assertEqual(humanize_direction(raw), "Rain lashes against the window.")

    def test_humanize_panels(self):
        panels = [
            {"image": "a.png", "direction": "In this shot, we see a testament to ancient ruins."},
            {"image": "b.png", "direction": "A delicate dance of light and shadow on concrete."}
        ]
        cleaned = humanize_panels(panels)
        self.assertEqual(cleaned[0]["direction"], "Evidence of ancient ruins.")
        self.assertEqual(cleaned[1]["direction"], "Stark light and deep shadows on concrete.")

    def test_clean_input_preservation(self):
        raw = "Medium shot: <Subject 1> turns around and racks the shotgun slide."
        self.assertEqual(humanize_direction(raw), raw)
        mouth = "The singer holds still, giving a sense of calm, lips sealed."
        self.assertEqual(humanize_direction(mouth), mouth)


if __name__ == "__main__":
    unittest.main()
