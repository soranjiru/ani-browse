import subprocess


def play_anime(title: str, prefer_dub: bool = False) -> int:
    cmd = ["ani-cli"]

    if prefer_dub:
        cmd.append("--dub")

    cmd.append(title)

    result = subprocess.run(cmd, check=False)
    return result.returncode