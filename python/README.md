# Instructions 

## [encode.py](./encode.py)

Made this script 4-5 years ago to help encode a lot of movies/video files so I can keep my media server low on used storage space.   
This script helps the user encode a singular video file or a bunch of video files inside a directory.   
Moves the file(s) to a destination directory while encoding and leaves it there.   

### Usage Example:
```bash
# Encodes a single file
python3 encode.py video_file1.mp4 /path/to/dir 

# Encodes videos files inside a directory
python3 encode.py -d sourceDirName destinationDirName

# Encodes them to a speicific bitrate (lessens the video quality and at the same time file size, default is 1500K)
python3 encode.py vid1.mp4 destDirName -b 500

And many more... check the table below.
```
#### Arguments:
| Argument | Purpose |
| --- | --- |
| `-d` or `--dir` | Indicate source is a directory |
| `-b` or `--bitrate` | Sets the bitrate for the output file | 
| `-y` or `--noconfirm` | Set true for overwrite and doesn't prompt you for input if destination directory has duplicate file |
| `-nm` or `--no-mail` | Disables the mail functionality |
| `--skip` | "Interactive to skip some files" is what the argument helper says.<br>Might have added this ages ago to make it so I can skip some times but never bothered adding the feature. |