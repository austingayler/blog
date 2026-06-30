"""
GitHub Git Data API client using githubkit.

Performs a single atomic commit containing all files for a post
(post.md + images) without touching a local git clone.

Sequence:
  1. GET ref → current commit SHA
  2. GET commit → base tree SHA
  3. POST blob for each file
  4. POST tree with all blobs
  5. POST commit
  6. PATCH ref to new commit SHA
"""

import base64
import logging
import os

from githubkit import GitHub

logger = logging.getLogger(__name__)


def _client() -> GitHub:
    return GitHub(os.environ["GITHUB_TOKEN"])


def _repo() -> tuple[str, str]:
    owner, repo = os.environ["GITHUB_REPO"].split("/", 1)
    return owner, repo


async def commit_post(
    post_dir: str,
    markdown: str,
    images: list[tuple[str, bytes]],  # [(filename, raw_bytes), ...]
    commit_message: str,
) -> str:
    """
    Commit post.md and all images under content/drafts/.../post_dir/
    Returns the URL of the new commit.
    """
    branch = os.environ.get("GITHUB_BRANCH", "main")
    owner, repo = _repo()
    gh = _client()

    # 1. Get current HEAD commit SHA
    ref_data = await gh.rest.git.async_get_ref(owner, repo, f"heads/{branch}")
    head_sha = ref_data.parsed_data.object_.sha

    # 2. Get base tree SHA from that commit
    commit_data = await gh.rest.git.async_get_commit(owner, repo, head_sha)
    base_tree_sha = commit_data.parsed_data.tree.sha

    # 3. Create blobs for all files
    tree_entries = []

    # Markdown blob (utf-8 text)
    md_blob = await gh.rest.git.async_create_blob(
        owner, repo,
        content=markdown,
        encoding="utf-8",
    )
    tree_entries.append({
        "path": f"{post_dir}/post.md",
        "mode": "100644",
        "type": "blob",
        "sha": md_blob.parsed_data.sha,
    })

    # Image blobs (base64 binary)
    for filename, raw in images:
        img_blob = await gh.rest.git.async_create_blob(
            owner, repo,
            content=base64.b64encode(raw).decode(),
            encoding="base64",
        )
        tree_entries.append({
            "path": f"{post_dir}/{filename}",
            "mode": "100644",
            "type": "blob",
            "sha": img_blob.parsed_data.sha,
        })

    # 4. Create new tree
    new_tree = await gh.rest.git.async_create_tree(
        owner, repo,
        base_tree=base_tree_sha,
        tree=tree_entries,
    )
    new_tree_sha = new_tree.parsed_data.sha

    # 5. Create commit
    new_commit = await gh.rest.git.async_create_commit(
        owner, repo,
        message=commit_message,
        tree=new_tree_sha,
        parents=[head_sha],
    )
    new_commit_sha = new_commit.parsed_data.sha

    # 6. Move ref
    await gh.rest.git.async_update_ref(
        owner, repo,
        ref=f"heads/{branch}",
        sha=new_commit_sha,
        force=False,
    )

    commit_url = new_commit.parsed_data.html_url
    logger.info("Committed post to %s", commit_url)
    return commit_url
