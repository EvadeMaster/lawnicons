from contextlib import contextmanager
from functools import lru_cache
import os
import re
import sys
import git
import datetime
import xml.etree.ElementTree as ET


LINK_THRESHOLD = os.getenv("RELEASE_LINK_THRESHOLD") or 20
NEW_THRESHOLD = os.getenv("RELEASE_NEW_THRESHOLD") or 100
DAY_THRESHOLD = os.getenv("RELEASE_DAY_THRESHOLD") or 1


REPOSITORY = os.getenv("REPOSITORY") or "."
SVG_PATH = os.getenv("PATH_TO_SVG") or os.path.join(REPOSITORY, "svgs")
APPFILTER_PATH = os.getenv("PATH_TO_APPFILTER") or os.path.join(REPOSITORY, "app", "assets", "appfilter.xml")


INCREMENT_TYPE = os.getenv("INCREMENT") or "default"
ICONS_CALCULATION_TYPE = os.getenv("ICONS_CALCULATION") or "default"


# Get the third most recent tag, which is the last release
# Don't use positive number (e.g., 0, 1, 2, etc) as it will be sorted in reverse
# [-1]: Nightly
# [-2]: v2.12.0 - last release
# [-3]: v2.11.0 - second last release
last_tag = sorted(
    git.Repo(REPOSITORY).tags, 
    key=lambda t: t.commit.committed_datetime
)[-2].name


@lru_cache()
def is_workflow_dispatch() -> bool:
    """
    Check if the event is manually dispatched, support GitHub/GitLab/Forgejo

    GITHUB_EVENT_NAME: GitHub Actions, Forgejo

    CI_PIPELINE_SOURCE: GitLab CI

    Returns:
        bool: True if the event is manually dispatched, False otherwise
    """

    if (
        os.getenv("GITHUB_EVENT_NAME") == "workflow_dispatch"
        or os.getenv("CI_PIPELINE_SOURCE") == "web"
    ):
        print("🔎 Manually triggered workflow detected!")
        return True
    return False


@contextmanager
def git_checkout(repo: git.Repo, ref: str):
    """
    Temporarily check out a specific git reference.

    Allow to check out a specific git reference temporarily and return to the
    original reference after the context manager exits.

    Args:
        repo (git.Repo): The git repository.
        ref (str): The reference to check out.

    Usage:
    ```py
      with git_checkout(repo, "v2.12.0"):
          # Do something
    ```
    """

    original_ref = (
        repo.active_branch.name if repo.head.is_detached else repo.head.ref.name
    )
    repo.git.checkout(ref)
    try:
        yield
    finally:
        repo.git.checkout(original_ref)


def is_greenlight(
    result: tuple, manually_triggered: bool, day_threshold=1, link_threshold=20, new_threshold=100
) -> bool:
    """Check if the new icons meet the threshold for release

    Args:
        result (list): List of new icons
        manually_triggered (bool): Check if the workflow is manually dispatched
        day_threshold (int, optional): Number of days to check. Defaults to 1.
        link_threshold (int, optional): Number of linked icons to check. Defaults to 20.
        new_threshold (int, optional): Number of new icons to check. Defaults to 100.

    Returns:
        bool: True if the new icons is eligible for release, False otherwise, will skip all checks if manually triggered.
    """

    if manually_triggered:
        print("🟢 Manually triggered workflow, skipped all check, greenlighting!")
        return True

    today_day = datetime.datetime.now().day
    if today_day != day_threshold:
        print(
            f"🔴 Today is {today_day}, which isn't the target release day {day_threshold}."
        )
        return False

    if len(result[0]) < new_threshold:
        print(
            f"🔴 Only {len(result[0])} new icons found since the last release, below the threshold of {new_threshold}."
        )
        return False
    if len(result[1]) < link_threshold:
        print(
            f"🔴 Only {len(result[1])} icons linked to a new component found since the last release, below the threshold of {link_threshold}."
        )
        return False

    print("🟢 Greenlight!")
    return True


def next_release_predictor(result: list, last_version: str, increment_type: str = "default") -> str:
    """
    Predict the next release version by incrementing the MAJOR, MINOR, or 
    PATCH component based on Semantic Versioning 2.0.0.

    **NOTE**: Doesn't support predicting the MAJOR component.

    If the number of new icons is more than the threshold, 
    it will increment the MINOR component otherwise PATCH component.

    Args:
        result (tuple): Tuple of new icons and linked icons
        last_version (str): Current version of the current.
        increment_type (str, optional): Component to increments.

    Raises:
        ValueError: If increment type is incorrect

    Returns:
        str: Next version
    """
    # Additional Note:
    # every MAJOR will increment the MAJOR and reset MINOR and PATCH component,
    # every MINOR will increment the MINOR and reset PATCH component,
    # every PATCH will only increment the PATCH component.

    increment_type = increment_type.lower()
    match = re.match(r"v(\d+)\.(\d+)\.(\d+)", last_version)
    if not match:
        raise ValueError(f"Invalid version format: {last_version}")

    major, minor, patch = map(int, match.groups())

    if len(result[0]) < NEW_THRESHOLD or len(result[1]) < LINK_THRESHOLD:
        increment_type = "patch"
    else:
        increment_type = "minor"

    if increment_type == "major":
        major += 1
        minor = 0
        patch = 0
    elif increment_type == "minor":
        minor += 1
        patch = 0
    elif increment_type == "patch":
        patch += 1
    else:
        raise ValueError(
            f"Invalid increment type: {increment_type}. Choose 'major', 'minor', or 'patch'."
        )

    return f"v{major}.{minor}.{patch}"


def release_parser(markdownfile: str) -> NotImplementedError:
    """
    Parse the release note and return the version number.

    Args:
        markdownfile (str): Path to the markdown file.

    Returns:
        str: Version number
    """
    with open(markdownfile, "r") as file:
        file.readlines()
    return NotImplementedError


class new_icon_since:
    """
    Get the new icons since the last release.

    This class provides two methods to get the new icons since the last release:
    - from_svg: Get the new icons based on amount of content in the folder.
    - from_appfilter: Get the new icons based on the appfilter.xml file.

    **NOTE**: from_svg doesn't returns the linked icons status.
    """
    def from_svg(folder_path: str, last_tag: str) -> tuple:
        """
        Compare current icons to {last_tag} based on amount of content in the folder.

        Checkout the {last_tag} and compare it with the current content in the folder.

        Args:
            folder_path (str): Path to the folder containing the icons.
            last_tag (str): The last release version.

        Returns:
            tuple: List of new icons.
        """
        print("⚠️ This method doesn't support linked icons status.")
        current_icons = set(os.listdir(folder_path))

        print(f"Checking out version {last_tag}")
        with git_checkout(git.Repo(REPOSITORY), last_tag):
            previous_icons = set(os.listdir(folder_path))

        print(f"📊 Total current icons: {len(current_icons)}")
        print(f"📊 Total previous icons: {len(previous_icons)}")

        return list(current_icons - previous_icons)

    def from_appfilter(xml_file: str, last_tag: str) -> tuple:
        """
        Compare current icons to {last_tag} based on the appfilter.xml file.

        Checkout the {last_tag} and compare it with the current appfilter.xml file.

        Args:
            xml_file (str): Path to the appfilter.xml file.
            last_tag (str): Last tag to compare.

        Returns:
            tuple: List of new icons and linked icons
        """
        current_icons = []
        previous_icons = []

        for _, elem in ET.iterparse(xml_file, events=("start",)):
            if elem.tag == "item":
                component = elem.get("component")
                drawable = elem.get("drawable")
                name = elem.get("name")
                icon = {
                    "component": component,
                    "drawable": drawable,
                    "name": name,
                }
                current_icons.append(icon)

        with git_checkout(git.Repo(REPOSITORY), last_tag):
            for _, elem in ET.iterparse(xml_file, events=("start",)):
                if elem.tag == "item":
                    component = elem.get("component")
                    drawable = elem.get("drawable")
                    name = elem.get("name")
                    icon = {
                        "component": component,
                        "drawable": drawable,
                        "name": name,
                    }
                    previous_icons.append(icon)

        current_icons_set = set(
            (icon["component"], icon["drawable"]) for icon in current_icons
        )
        previous_icons_set = set(
            (icon["component"], icon["drawable"]) for icon in previous_icons
        )

        # This prone to `TypeError: unhashable type: 'dict'` for no reason
        new_icons_set = current_icons_set - previous_icons_set

        previous_drawables_set = set(icon["drawable"] for icon in previous_icons)

        linked_icons_set = set()
        true_new_icons_set = set()
        for component, drawable in new_icons_set:
            if drawable in previous_drawables_set:
                linked_icons_set.add((component, drawable))
            else:
                true_new_icons_set.add((component, drawable))

        true_new_icons_list = [
            {"component": component, "drawable": drawable}
            for component, drawable in true_new_icons_set
        ]
        linked_icons_list = [
            {"component": component, "drawable": drawable}
            for component, drawable in linked_icons_set
        ]

        return true_new_icons_list, linked_icons_list


if ICONS_CALCULATION_TYPE.lower() == "svgs":
    result = new_icon_since.from_svg(SVG_PATH, last_tag)
else:
    result = new_icon_since.from_appfilter(APPFILTER_PATH, last_tag)


print(f"🎉 There have been {len(result[0])} new icons since release!")
print(f"🔗 {len(result[1])} icons have been linked to a new component since release!")

greenlight = is_greenlight(result, is_workflow_dispatch(), DAY_THRESHOLD, LINK_THRESHOLD, NEW_THRESHOLD)
print(
    f"🚦 {'Not eligible for release!' if not greenlight else 'Eligible for release! Greenlight away!'}"
)


next_version = next_release_predictor(result, last_tag, INCREMENT_TYPE)
print(f"{next_version}")
print(f"{str(greenlight).lower()}")


github_output = os.environ.get("GITHUB_OUTPUT")
if github_output:
    with open(github_output, "a") as output_file:
        print(f"next_version={next_version}", file=output_file)
        print(f"greenlight={str(greenlight).lower()}", file=output_file)
else:
    print("GITHUB_OUTPUT environment variable is not set.", file=sys.stderr)


exit(1 if not greenlight else 0)
