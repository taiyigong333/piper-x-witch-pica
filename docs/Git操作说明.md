# Git 操作说明

本文说明本项目的日常 Git 操作。命令默认在仓库根目录执行：

```bash
cd /home/cv/gcj/project/data_collect/piper-x-witch-pica
```

## 查看状态

```bash
git status --short --branch
git log --oneline --decorate -5
git remote -v
```

## 创建提交

```bash
git diff
git diff --check
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/python -m pytest -q
git add <文件或目录>
git commit -m "简短、明确的变更说明"
git show --stat --oneline HEAD
```

推荐只暂存本次任务相关文件。

## 分支操作

```bash
git branch -vv
git branch -a
git switch -c feature/<名称>
git switch <分支名>
```

本项目当前工作分支为 `Reverse-recording`：

```bash
git push origin Reverse-recording:Reverse-recording
```

## Tag 操作

```bash
git tag --list
git show tag0.5
```

只有明确要求发布新版本时才创建或更新 tag：

```bash
git tag -a tag0.6 -m "release tag0.6"
git push origin tag0.6:tag0.6
```

已发布的 `tag0.5` 不要重复移动或覆盖。普通代码修改只提交并推送分支即可。

## SSH 推送

```bash
git remote set-url origin git@github.com:taiyigong333/piper-x-witch-pica.git
ssh -T git@github.com
```

需要指定私钥时，可对当前命令临时指定：

```bash
GIT_SSH_COMMAND='ssh -i /home/cv/gcj/project/temp/pris709 -o IdentitiesOnly=yes -o StrictHostKeyChecking=accept-new' \
git push origin Reverse-recording:Reverse-recording
```

出现 `Permission denied (publickey)` 时，检查私钥路径、权限、GitHub 账号绑定和仓库写权限；不要把私钥提交到仓库。

## 拉取更新

```bash
git fetch origin
git log --oneline HEAD..origin/Reverse-recording
git pull --ff-only origin Reverse-recording
```

## 冲突处理

```bash
git status
git diff
```

手工解决冲突并删除冲突标记后：

```bash
git add <已解决的文件>
git commit
```

未提交的合并过程可以使用：

```bash
git merge --abort
```

不要使用 `git reset --hard` 或 `git checkout --` 覆盖未确认的用户修改。

## 本项目推荐流程

```bash
git status --short --branch
git diff --check
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/python -m pytest -q
git add <本次变更>
git commit -m "<变更说明>"
git push origin Reverse-recording:Reverse-recording
```

只有用户明确要求发布版本时，再额外执行 tag 创建和 tag 推送。
