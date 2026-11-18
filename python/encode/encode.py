import os
import re
import sys
import math
import time
import dotenv
import ffmpeg
import shutil
import argparse
import threading
import subprocess
import logging as logger
from mailer import mail
from dataclasses import dataclass
from progress import ProgressTracker
from typing import Dict, Any, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed



dotenv.load_dotenv()

def setup_logger(log_file="encode.log", logger=logger):
    log_level = logger.DEBUG
    logg = logger.getLogger(__name__)
    logg.setLevel(log_level)

    if not logg.handlers:
        console_handler = logger.StreamHandler()
        file_handler = logger.FileHandler(log_file)

        console_handler.setLevel(log_level)
        file_handler.setLevel(log_level)

        formatter = logger.Formatter("%(asctime)s - %(levelname)s - %(message)s")
        console_handler.setFormatter(formatter)
        file_handler.setFormatter(formatter)

        logg.addHandler(console_handler)
        logg.addHandler(file_handler)

    return logg


logging = setup_logger()
extensions = [".mp4",".avi",".mov",".mkv",".flv",".wmv",".webm",".m4v",".mpg",".mpeg",".3gp",".ogv",".ts",".rm",".rmvb",".vob",".m2ts",".mts",".divx",".f4v",".asf"]
hevc_supported = [".mp4",".mov",".webm",".ts",".m2ts",".mts",".3gp",".ogv"]
hevc_not_supported = [".avi",".flv",".wmv",".m4v",".mpg",".mpeg",".rm",".rmvb",".vob",".divx",".f4v",".asf"]
resolutions = {"1080": 1080,"720": 720,"540": 540,"480": 480,"360": 360,"240": 240}

DEFAULT_CQ = 30
DEFAULT_MAXRATE_K = 1500
FFMPEG_BIN = os.environ.get("FFMPEG_BIN", shutil.which("ffmpeg"))
DECODE_ERROR_MARKERS = (
    "Error submitting packet",
    "Invalid data found when processing input",
)

def parse_fps(rate: str) -> float:
    """Parse ffprobe's '30000/1001' style frame rate without eval()."""
    num, _, den = str(rate).partition("/")
    den = float(den) if den else 1.0
    return float(num) / den if den else 0.0


@dataclass
class Colors:
    HEADER = "\033[95m"
    OKBLUE = "\033[94m"
    OKCYAN = "\033[96m"
    OKGREEN = "\033[92m"
    WARNING = "\033[93m"
    FAIL = "\033[91m"
    ENDC = "\033[0m"
    BOLD = "\033[1m"
    UNDERLINE = "\033[4m"


@dataclass
class VideoDetails:
    resolution: str
    bitrate: str
    # maxrate: str
    framerate: int
    ratio: str
    fname: str
    color: str
    w: str
    h: str

    def _parse_bitrate(self, bitrate: str) -> int:
        match = re.match(
            r"(\d+)([kKmM]?)?", bitrate
        )  # [Bb][Pp][Ss]? what is this comment? Idr this shit.
        if not match and not match.groups():
            return 1500

        match = match.groups()
        if match[-1] not in ["K", "k"]:
            return 1500

        return int(match[0])

    def compare_bitrate(self, user_bitrate: str = "1500K") -> bool:
        video_bitrate = self._parse_bitrate(self.bitrate)
        user_bitrate = self._parse_bitrate(user_bitrate)

        return video_bitrate > user_bitrate

    @classmethod
    def init(cls, d: Dict[str, Any], **kwargs) -> "VideoDetails":
        try:
            w = int(d.get("width"))
            h = int(d.get("height"))
            res = f"{w}:{h}"

            gcd = math.gcd(w, h)
            ratio = f"{w//gcd}:{h//gcd}"

            fr = round(parse_fps(d.get("r_frame_rate")), 2)

            try:
                br = "{}K".format(int(d.get("bit_rate")) // 1000)
            except TypeError:
                fmt = kwargs.get("format", {})
                fmt_bitrate = fmt.get("bit_rate")
                if fmt_bitrate:
                    br = "{}K".format(int(fmt_bitrate) // 1000)
                else:
                    duration = d.get("duration") or fmt.get("duration")
                    if duration:
                        filesize = os.path.getsize(
                            os.path.join(kwargs.get("source_dir"), d.get("file_name"))
                        )
                        br = "{}K".format(int((filesize * 8) / float(duration)) // 1000)
                    else:
                        br = "1500K"
            print(
                f"{{Width: {w}, Height: {h}, Res: {res}, ratio: {ratio}, frame_rate: {fr}, bit_rate: {br}"
            )
            return cls(
                resolution=res,
                bitrate=br,
                framerate=fr,
                ratio=ratio,
                fname=d.get("file_name"),
                w=str(w),
                h=str(h),
                color=d.get('color_transfer')
            )
        except Exception as e:
            exc_info = sys.exc_info()
            error_message = f"{e}. Error occured inside VideoDetails class when initializing, Error Type: {exc_info[0]}, Code line: {exc_info[2].tb_lineno}. VideoDetails: {d}"
            logging.error(error_message)
            mail(sDir=kwargs.get("source_dir"), error=error_message)


class ArgumentHandler:
    def __init__(self):
        self.source = None
        self.destination = None
        self.dest_files = list()
        self.bit_rate = str()
        self.cq = DEFAULT_CQ
        self.res = None
        self.jobs = 1
        self.recursive = False
        self.parser = argparse.ArgumentParser(
            description="Encode 4k video files down to 1080p."
        )
        self.is_directory = False
        self.overwrite = False
        self.no_mail = False
        self.hdr2sdr = False

    def initialize(self) -> None:
        self.parser.add_argument(
            "-d", "--dir", action="store_true", help="Indicate source is directory."
        )
        self.parser.add_argument(
            "source",
            type=str,
            help="Source file / Source directory to be encoded.",
        )
        self.parser.add_argument(
            "dest",
            type=str,
            nargs="?",
            help="Destination directory / Directory where encoded files go to.",
        )
        self.parser.add_argument(
            "-b",
            "--bitrate",
            type=int,
            help=f"Maximum video bitrate (ceiling) in kb/s, without the K. i.e., 2000. Default: {DEFAULT_MAXRATE_K}. "
            "The encoder goes lower whenever the content allows it.",
        )
        self.parser.add_argument(
            "--cq",
            type=int,
            choices=range(0, 52),
            metavar="0-51",
            default=DEFAULT_CQ,
            help=f"Constant quality level. Lower = better quality / bigger file. Default: {DEFAULT_CQ}. Try 28-32.",
        )
        self.parser.add_argument(
            "-h2s",
            '--hdr2sdr',
            action="store_true",
            help="Tonemap HDR files to 8-bit SDR and encode them on the GPU (fast),"
            "instead of keeping the HDR with the CPU encoder (slow)"
        )
        # self.parser.add_argument(
        #     '--logfile', type=str, help='Location for logfile'
        # )
        self.parser.add_argument(
            "-y", "--noconfirm", action="store_true", help="Overwrite files"
        )

        self.parser.add_argument(
            "-nm", "--no-mail", action="store_true", help="Parse to not mail."
        )
        self.parser.add_argument(
            "--skip", action="store_true", help="Interactive to skip some files"
        )
        self.parser.add_argument(
            "-r",
            "--res",
            type=str,
            choices=list(resolutions.keys()),
            help="Short side of the output resolution, e.g. 720 for 1280x720 (or 720x1280 vertical). "
            "Never upscales. Default: 1080.",
        )
        self.parser.add_argument(
            '-j', '--jobs', type=int, default=1, metavar='1-4', help="Number for files to encode in parallel (directory mode). Default: 1"
        )

        self.parser.add_argument(
            "-R",
            "--recursive",
            action="store_true",
            help="Also encode videos in subdirectories of the source directory (requires -d). "
            "The folder structure is recreated inside the destination.",
        )

        args = self.parser.parse_args()
        if args.recursive and not args.dir:
            self.parser.error("-R/--recursive can only be used together with -d/--dir")

        self.source = args.source
        self.destination = args.dest
        self.is_directory = args.dir
        self.overwrite = args.noconfirm
        self.no_mail = args.no_mail
        self.res = args.res
        self.cq = args.cq
        self.jobs = args.jobs
        self.recursive = args.recursive
        self.hdr2sdr = args.hdr2sdr
        
        if self.hdr2sdr and not self.ffmpeg_has_filters('zscale', 'tonemap'):
            logging.error('--hdr2sdr needs the zscale and tonemap filters which this ffmpeg build lacks (rebuild with --enable-libzimg)')
            exit(1)
        
        if not args.bitrate or args.bitrate <= 0:
            self.bit_rate = f"{DEFAULT_MAXRATE_K}K"
        else:
            self.bit_rate = f"{args.bitrate}K"
    

        if self.is_directory:
            if not os.path.isdir(self.source):
                raise OSError(
                    f"{Colors.FAIL}Source directory: {self.source} is not available.\n\
                    Please double check provided directory path.{Colors.ENDC}"
                )
        else:
            if not os.path.isfile(self.source):
                raise OSError(
                    f"{Colors.FAIL}Source file: {self.source} is not available.\n\
                    Please double check provided file path.{Colors.ENDC}"
                )

        if self.destination is None:
            destination = self.source.split(os.sep)
            destination[-1] = destination[-1].replace(" ", "_")
            destination = f"{os.sep}".join(destination)

            print(
                f"{Colors.WARNING}Argument destination is not supplied, suggest directory: {destination}.\n\
                      Want to proceed with this? (Y/N)",
                end=":",
            )

            if input(" ").lower() == "n":
                print(f"Then please make directory and provide destination directory.")

            self.destination = destination
            os.mkdir(destination)

            print(
                f"{Colors.OKGREEN}Destination directory {self.destination} successfully created.{Colors.ENDC}"
            )

            return

        elif not os.path.isdir(self.destination):
            print(
                f"{Colors.WARNING}Destination directory: {self.destination} is not available.\n\
                Create directory? (Y/N){Colors.ENDC}",
                end=":",
            )

            user_input = input()

            if user_input.lower() == "y":
                os.mkdir(self.destination)
                print(f"Destination directory created successfully.")
            elif user_input.lower() == "n":
                print(
                    f"{Colors.OKCYAN}Please create destination and provide with available destination directory next time. Exiting Script now.{Colors.ENDC}"
                )
                exit()
            return

        self.dest_files = os.listdir(self.destination)
        
    @staticmethod
    def ffmpeg_has_filters(*names) -> bool:
        out = subprocess.run([FFMPEG_BIN, '-hide_banner', '-filters'],
                             capture_output=True, text=True).stdout
        return all(re.search(rf'\s{n}\s', out) for n in names)


class VideoEncoder(ArgumentHandler):
    def __init__(self):
        super().__init__()
        self.remove_file = bool()
        self.suppress_item_mail = False
        self.skip_input = False
        self._hdr_confirmed = None
        self._confirm_lock = threading.Lock()
        self.tracker = ProgressTracker()

    def process_file(self, source_file: str, label: Optional[int] = None) -> str:
        """Build the output file name. `label` is the real output height label
        (e.g. 720) used to rewrite '2160p'/'1080p' style tags in the name."""
        name = os.path.basename(source_file)
        name = re.sub(r"\.\d{2}\.\d{2}\.\d{2}", "", name)
        if label:
            name = re.sub(
                r"(?i)(?<![0-9a-z])(?:2160|1440|1080|720|540|480|360|240)p(?![0-9a-z])",
                f"{label}p",
                name,
            )
        if not any(name.lower().endswith(ext) for ext in hevc_supported):
            name = f"{os.path.splitext(name)[0]}.mp4"
        return name

    @staticmethod
    def fit_resolution(w: int, h: int, target: int) -> str:
        """Scale so the SHORT side equals `target`, keep the aspect ratio,
        keep both sides even, and never upscale."""
        short = min(w, h)
        if short <= target:
            return f"{w}x{h}"
        scale = target / short
        nw = round(w * scale / 2) * 2
        nh = round(h * scale / 2) * 2
        return f"{nw}x{nh}"
    
    @staticmethod
    def dynamic_range(video_metadata: dict) -> str:
        pix_fmt = video_metadata.get("pix_fmt", "")
        transfer = video_metadata.get("color_transfer", "")

        if transfer in ("smpte2084", "arib-std-b67"):
            return "hdr"
        if re.search(r"(9|10|12|14|16)(le|be)$", pix_fmt):
            return "sdr10"
        return "sdr8"

    @staticmethod
    def get_video_stream(streams) -> dict:
        for stream in streams:
            if stream["codec_type"] == "video":
                return stream
    
    def confirm_hdr_quality(self) -> bool:
        with self._confirm_lock:
            if self._hdr_confirmed is None:
                if self.skip_input:
                    self._hdr_confirmed = True
                else:
                    answer = self.tracker.ask(
                        f'CRF {self.cq} for HDR files may look bad. Continue? (y/n):'
                    ).lower()
                    self._hdr_confirmed = (answer == 'y')
            return self._hdr_confirmed

    def delete_file(self, path: str) -> None:
        logging.info(f"Removing original file: {path}")
        os.remove(path)

    def find_videos(self) -> list:
        """Return [(source_path, output_dir), ...] for the source directory.
        With -R the sub-folder layout is mirrored under the destination."""
        src_root = os.path.abspath(self.source)
        dest_root = os.path.abspath(self.destination)
        dest_real = os.path.realpath(self.destination)
        found = []
        for root, dirs, names in os.walk(src_root):
            # If the destination lives inside the source, never walk into it,
            # otherwise already-encoded files would be encoded again.
            dirs[:] = sorted(
                d
                for d in dirs
                if os.path.realpath(os.path.join(root, d)) != dest_real
            )
            rel = os.path.relpath(root, src_root)
            out_dir = dest_root if rel == "." else os.path.join(dest_root, rel)
            for name in sorted(names):
                if any(name.lower().endswith(ext) for ext in extensions):
                    found.append((os.path.join(root, name), out_dir))
            if not self.recursive:
                break  # top level only
        return found

    def encode_file(self, source=None, remove=None, out_dir=None) -> Optional[dict]:
        if source is None:
            source = self.source
        if out_dir is None:
            out_dir = self.destination

        if remove is None:
            remove = input("Delete file after encode completion? (y/n): ").lower()
        if remove == "y":
            self.remove_file = True
        else:
            self.remove_file = False
            if remove != "n":
                print(
                    "Input is neither y or n, will leave the file untouched after encode."
                )

        file_name = os.path.basename(source)
        # In directory mode show the path relative to the source folder, so equal
        # names in different sub-folders can be told apart in logs and emails.
        display_name = (
            os.path.relpath(source, self.source) if self.is_directory else file_name
        )
        try:
            size_mb = lambda s: round(s / 1000 / 1000, 2)

            probed_data = ffmpeg.probe(source)
            fmt = probed_data.get("format", {})
            video_metadata = self.get_video_stream(probed_data["streams"])
            video_metadata["file_name"] = file_name
            original_video_metadata = VideoDetails.init(
                video_metadata,
                source_dir=os.path.dirname(source),
                format=fmt,
            )
            original_size = size_mb(os.path.getsize(source))
            duration = float(fmt.get("duration") or video_metadata.get("duration") or 0)
            dynamic_range = self.dynamic_range(video_metadata)

            w, h = video_metadata["width"], video_metadata["height"]
            target = resolutions[self.res] if self.res else 1080
            video_resolution = self.fit_resolution(w, h, target)
            downscaled = min(w, h) > target

            video_framerate = min(parse_fps(video_metadata["r_frame_rate"]), 30)
            maxrate_k = int(self.bit_rate.rstrip("Kk"))

            output_path = os.path.join(
                out_dir,
                self.process_file(file_name, target if downscaled else None),
            )
            if os.path.abspath(output_path) == os.path.abspath(source):
                raise ValueError(
                    f"Output path equals the source file ({source}). "
                    "Use a different destination directory."
                )
            os.makedirs(out_dir, exist_ok=True)  # mirrored sub-folder in destination

            logging.info(f"Encoding file: {source}")
            logging.info(f"Size of original file: {original_size} MB")
            logging.info(f"Original File Metadata: {original_video_metadata}")
            logging.info(
                f"Encoding Parameters: {video_resolution}, FrameRate: {video_framerate}, "
                f"CQ: {self.cq}, MaxRate: {maxrate_k}K"
            )

            params = dict(
                s=video_resolution,
                fps_mode="vfr",
                ac=2,
                audio_bitrate="128K",
            )
            if dynamic_range == 'hdr' and not self.hdr2sdr:
                if self.cq > 26 and not self.confirm_hdr_quality():
                    logging.warning(f'Skipping {file_name}: HDR with CRF {self.cq} not confirmed.')
                    return None
                color = video_metadata.get('color_transfer')
                x265 = f"colorprim=bt2020:transfer={color}:colormatrix=bt2020nc:repeat-headers=1:vbv-maxrate={maxrate_k}:vbv-bufsize={maxrate_k*2}"
                if color == 'smpte2084':
                    x265 += ":hdr10=1"
                params.update(
                    dict(
                        vcodec="libx265",
                        pix_fmt="yuv420p10le",
                        crf=self.cq,
                        preset="medium",

                        **{"tag:v": "hvc1"},
                        **{"x265-params": x265},
                    )
                )
                logging.info(
                    "Encoder: libx265 (CPU)"
                    f"\nVideo File is {dynamic_range.upper()}."
                )
            else:                    
                params.update(
                    dict(
                        vcodec="hevc_nvenc",
                        video_bitrate="0",
                        rc="vbr",
                        preset="p7",
                        pix_fmt="yuv420p",
                        cq=self.cq,       
                        tune="hq",
                        maxrate=f"{maxrate_k}K",
                        bufsize=f"{maxrate_k * 2}K")
                )
                if dynamic_range == "hdr":
                    w, h = video_resolution.split("x")
                    params.pop("s")
                    params.update(
                        vf=(
                            f"scale={w}:{h},"
                            f"zscale=tin={original_video_metadata.color}:min=bt2020nc:pin=bt2020:rin=tv:t=linear:npl=100,"
                            "format=gbrpf32le,zscale=p=bt709,"
                            "tonemap=tonemap=hable:desat=0,"
                            "zscale=t=bt709:m=bt709:r=tv,format=yuv420p"
                            ),
                        color_primaries="bt709", color_trc="bt709",
                        colorspace="bt709", color_range="tv"
                        )
                logging.info(
                    "Encoder: hevc_nvenc"
                    f"\nVideo File is {dynamic_range.upper()}"
                )
            try:
                print("\nPress Enter at any time to see progress")
                encode_start = time.perf_counter()
                _, err = self.tracker.run(
                    ffmpeg.input(source)
                    .output(output_path, **params),
                    cmd=FFMPEG_BIN,
                    name=display_name, 
                    duration=duration
                )
                encode_end = time.perf_counter()
                err_text = err.decode("utf-8", errors="replace") if err else ""
                bad_packets = err_text.count(DECODE_ERROR_MARKERS[0])

                out_size = os.path.getsize(output_path)
                avg_bitrate = (
                    f"{int(out_size * 8 / duration / 1000)}K" if duration else "n/a"
                )
                logging.info(f"Encoding of {source} done.")
                logging.info(
                    f"Size of output file: {size_mb(out_size)} MB, average bitrate: {avg_bitrate}"
                )

                warning = None
                if bad_packets or any(m in err_text for m in DECODE_ERROR_MARKERS):
                    warning = (
                        f"Source has damaged data ({bad_packets} bad packet(s)); "
                        "output may have glitches. Original file was NOT deleted."
                    )
                    logging.warning(f"{file_name}: {warning}")
                    logging.warning(f"ffmpeg stderr tail:\n{err_text[-1500:]}")

                if self.remove_file and not warning:
                    self.delete_file(source)

                logging.info(f"Encoding of {source} completed.")
                mail_details = dict(
                    file_name=display_name,
                    bit_rate=avg_bitrate,
                    size=size_mb(out_size),
                    original_size=original_size,
                    warning=warning,
                    time_elapsed=round((encode_end-encode_start)/60, 2)
                )
                mail(
                    source,
                    nomail=self.no_mail or self.suppress_item_mail,
                    maxrate=self.bit_rate,
                    cq=self.cq,
                    files=[mail_details],
                )
                return mail_details

            except ffmpeg.Error as e:
                ffmpeg_err = (
                    e.stderr.decode("utf-8", errors="replace")
                    if e.stderr
                    else "No stderr output"
                )
                logging.error(f"FFmpeg error on {source}:\n{ffmpeg_err}")
                logging.error(f"video_metadata = {video_metadata}")
                if os.path.exists(output_path):
                    logging.info(f"Removing incomplete output: {output_path}")
                    os.remove(output_path)
                mail(source, error=ffmpeg_err[-3000:], nomail=self.no_mail)
                exit()
        except Exception as e:
            exc_tb = sys.exc_info()[2]
            error_message = (
                f"{e}\nError occured in function encode_file, Line: {exc_tb.tb_lineno}"
            )
            logging.error(error_message)
            mail(source, error=error_message, nomail=self.no_mail)

    def encode_files(self) -> None:
        videos = self.find_videos()
        files_count = len(videos)
        if not files_count:
            logging.warning(f"No video files found in {self.source}")
            return

        folders = len({out_dir for _, out_dir in videos})
        self.tracker.set_total(files_count)
        logging.info(
            f"Found {files_count} video(s) in {folders} folder(s)"
            f"{' (recursive)' if self.recursive else ''}."
        )

        files_data = []
        processed_files = 0
        self.suppress_item_mail = True
        encode_start = time.perf_counter()
        remove = input("Delete files after encode completion? (y/n): ").lower()

        with ThreadPoolExecutor(max_workers=self.jobs) as pool:
            futures = [
                pool.submit(self._safe_encode, path, remove, out_dir)
                for path, out_dir in videos
            ]
            for future in as_completed(futures):
                result = future.result()
                if result:
                    files_data.append(result)
                processed_files += 1
                logging.info(f"Processed {processed_files}/{files_count} files.")

        time_elapsed = round((time.perf_counter() - encode_start)/60, 2)
        self.suppress_item_mail = False
        mail(
            self.source,
            nomail=self.no_mail,
            maxrate=self.bit_rate,
            cq=self.cq,
            files=files_data,
            time_elapsed=time_elapsed
        )

    def _safe_encode(self, path, remove, out_dir=None):
        try:
            return self.encode_file(source=path, remove=remove, out_dir=out_dir)
        except SystemExit:
            return None


def delete_dir(source) -> None:
    screens = [
        ["screens"],
        ["screen"],
        ["Screen"],
        ["Screens"],
        ["_screen"],
        ["_screens"],
        ["_Screens"],
        ["_Screen"],
    ]
    if any(
        os.listdir(source) == dirSt for dirSt in screens
    ):  # this check if the only subdir in the directory is a screen directory
        for root, dirs, files in os.walk(source):
            if root != source:
                for fil in files:
                    os.remove(os.path.join(root, fil))
                for d in dirs:
                    for r, sd, fs in os.walk(os.path.join(root, d)):
                        for f in fs:
                            os.remove(os.path.join(root, f))
                        os.rmdir(r)
                os.rmdir(root)

        logging.info(f"{source}'s screens directory deleted successfully.")
    else:
        logging.info(
            f"{source} has subdirectories other than screens. Please check them out."
        )
        return

    os.rmdir(source)
    logging.info(f"{source} directory removed.")


def main() -> None:
    encoder = VideoEncoder()
    encoder.initialize()
    try:
        if encoder.is_directory:
            encoder.encode_files()
        else:
            encoder.encode_file()

    except KeyboardInterrupt:
        print("User cancellation.")
        exit()
    except Exception as e:
        exc_tb = sys.exc_info()[2]
        error_message = f"{e} (Error Code Line:{exc_tb.tb_lineno})"
        logging.error(error_message)
        mail(encoder.source, error=error_message, nomail=encoder.no_mail)


if __name__ == "__main__":
    main()
