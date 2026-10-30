import os
import re
import ffmpeg
import logging as logger
import argparse
from dataclasses import dataclass
import re
import math
import smtplib
import traceback
from typing import Dict, Any, Optional
import sys
import dotenv

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
extensions = [
    ".mp4",
    ".avi",
    ".mov",
    ".mkv",
    ".flv",
    ".wmv",
    ".webm",
    ".m4v",
    ".mpg",
    ".mpeg",
    ".3gp",
    ".ogv",
    ".ts",
    ".rm",
    ".rmvb",
    ".vob",
    ".m2ts",
    ".mts",
    ".divx",
    ".f4v",
    ".asf",
]
hevc_supported = [
    ".mp4",
    ".mov",
    ".webm",
    ".ts",
    ".m2ts",
    ".mts",
    ".3gp",
    ".ogv",
]
hevc_not_supported = [
    ".avi",
    ".flv",
    ".wmv",
    ".m4v",
    ".mpg",
    ".mpeg",
    ".rm",
    ".rmvb",
    ".vob",
    ".divx",
    ".f4v",
    ".asf",
]


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

    def _parse_bitrate(self, bitrate: str) -> int:
        match = re.match(r"(\d+)([kKmM]?)?", bitrate)  # [Bb][Pp][Ss]? what is this comment? Idr this shit.
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

            fr = round(eval(d.get("r_frame_rate")), 2)

            try:
                br = "{}K".format(int(d.get("bit_rate")) // 1000)
            except TypeError:
                fmt = kwargs.get('format', {})
                fmt_bitrate = fmt.get('bit_rate')
                if fmt_bitrate:
                    br = "{}K".format(int(fmt_bitrate)//1000)
                else:
                    duration = d.get('duration') or fmt.get('duration')
                    if duration:
                        filesize = os.path.getsize(os.path.join(kwargs.get('source_dir'), d.get('file_name')))
                        br = '{}K'.format(int((fiesize * 8) / float(duration)) // 1000)
                    else:
                        br = "1500K"
            print(f'{{Width: {w}, Height: {h}, Res: {res}, ratio: {ratio}, frame_rate: {fr}, bit_rate: {br}')
            return cls(resolution=res, bitrate=br, framerate=fr, ratio=ratio, fname=d.get('file_name'))
        except Exception as e:
            exc_info = sys.exc_info()
            error_message = f'{e}. Error occured inside VideoDetails class when initializing, Error Type: {exc_info[0]}, Code line: {exc_info[2].tb_lineno}. VideoDetails: {d}'
            logging.error(error_message)
            mail(sDir = kwargs.get('source_dir'), error = error_message)

class ArgumentHandler:
    def __init__(self):
        self.source = None
        self.destination = None
        self.dest_files = list()
        self.bit_rate = str()
        self.parser = argparse.ArgumentParser(
            description="Encode 4k video files down to 1080p."
        )
        self.is_directory = False
        self.overwrite = False
        self.no_mail = False

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
            help="BitRate you want to use for encoding. i.e., 2000 (without the K).",
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
            '--skip', action="store_true", help='Interactive to skip some files'
        )

        args = self.parser.parse_args()

        self.source = args.source
        self.destination = args.dest
        self.is_directory = args.dir
        self.overwrite = args.noconfirm
        self.no_mail = args.no_mail
        if not args.bitrate:
            self.bit_rate = f"1500K"
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


class VideoEncoder(ArgumentHandler):
    def __init__(self):
        super().__init__()
        self.remove_file = bool()

    def process_file(self, source_file: str) -> str:
        source = re.sub(r"\.\d{2}\.\d{2}\.\d{2}", "", source_file).replace("2160p", "1080p").split(os.sep)[-1]
        if not any(source.endswith(ext) for ext in hevc_supported):
            source = f"{os.path.splitext(source)[0]}.mp4"
        return source

    @staticmethod
    def get_ratio(video_metadata) -> str:
        width = video_metadata["width"]
        height = video_metadata["height"]
        gcd = math.gcd(width, height)
        return f"{width//gcd}:{height//gcd}"

    @classmethod
    def get_resolution(cls, video_meta) -> str:
        vrs = ["9:16", "2:3", "3:4", "4:5", "5:8", "10:16", "9:18", "1:2"]
        ratio = cls.get_ratio(video_meta)
        w, h = video_meta["width"], video_meta["height"]

        isV = ratio in vrs or w < h
        isH = not isV

        if (isV and w > 1080) or (isH and h > 1080):
            w = w // 2
            h = h // 2

        return f"{w}:{h}"

    @staticmethod
    def get_video_stream(streams) -> dict:
        for stream in streams:
            if stream["codec_type"] == "video":
                return stream

    def delete_file(self, ogFile) -> None:
        logging.info(f"Removing original file: {ogFile}")
        os.remove(os.path.join(self.source, ogFile))
        
        
    def encode_file(self, source = None, remove = None) -> None:
        if source is None:
            source = self.source
            
        # if source in self.dest_files:
        #     print(
        #         f"{Colors.WARNING}File {source} already exists in destination directory. Do you want to overwrite? (y/n){Colors.ENDC}",
        #         end=":",
        #     )
        #     overwrite = input(" ")
        #     if overwrite.lower() == "n":
        #         logging.info(f"File {source} already exists in destination directory. Skipping encoding.")
        #         return
        #     elif overwrite.lower() == "y":
        #         logging.info(f"File {source} already exists in destination directory. Overwriting file.")
        #     else:
        #         logging.info(f"Input is neither y or n, will leave the file untouched after encode.")
        #         return 
        if remove is None:
            remove = input("Delete file after encode completion? (y/n): ").lower()
        if remove == "y":
            self.remove_file = True
        elif remove == "n":
            self.remove_file = False
        else:
            print(
                "Input is neither y or n, will leave the file untouched after encode."
            )
        try:
            sizeConvertion = lambda s: round(s / 1000 / 1000, 2)

            probed_data = ffmpeg.probe(source)
            video_metadata = self.get_video_stream(probed_data['streams'])
            video_metadata['file_name'] = source.split(os.sep)[-1]
            original_video_metadata = VideoDetails.init(
                video_metadata, 
                source_dir=source.rsplit(os.sep, 1)[0], 
                format=probed_data.get('format', '')
                )

            video_ratio = self.get_ratio(video_metadata)
            video_resolution = self.get_resolution(video_metadata)

            video_framerate = (
                round(eval(video_metadata["r_frame_rate"]), 2)
                if eval(video_metadata["r_frame_rate"]) < 30
                else 30
            )
            try:
                video_bitrate = (
                    "{}K".format(int(video_metadata["bit_rate"]) // 1000)
                    if (int(video_metadata["bit_rate"]) // 1000) < int(self.bit_rate.replace("K", ""))
                    else self.bit_rate
                )
                video_maxrate = (
                    "{}K".format(int(video_bitrate.replace("K", "")) + 100)
                    if int(video_metadata["bit_rate"]) // 1000 < int(self.bit_rate.replace("K", ""))
                    else f"{int(self.bit_rate.replace('K', '')) + 200}K"
                )
            except KeyError:
                video_bitrate = self.bit_rate
                video_maxrate = f"{int(self.bit_rate.replace('K', '')) + 200}K"
            except ValueError:
                mail(
                    self.source,
                    error="A vertical video has come up. Please test ratio function whenever you can.",
                    nomail=self.no_mail,
                )

            input_path = source
            output_path = os.path.join(self.destination, self.process_file(source.split(os.sep)[-1]))

            logging.info(f"Encoding file: {source}")
            logging.info(
                f"Size of original file: {sizeConvertion(os.path.getsize(input_path))} MiB "
            )
            logging.info(
                f"Original File Metadata: Resolution: {original_video_metadata}"
            )
            logging.info(
                f"Encoding Parameters: {video_resolution}, FrameRate: {video_framerate}, BitRate: {video_bitrate}"
            )
            
            params = dict(
                s=video_resolution,
                #r=video_framerate,
                vcodec="hevc_nvenc",
                video_bitrate=video_bitrate,
                maxrate=video_maxrate,
                rc="cbr",
                audio_bitrate="96K",
                fps_mode="vfr"
                #loglevel='ve',
            )
            
            try:
                ffmpeg.input(input_path).output(
                    output_path,
                    **params
                ).run(overwrite_output=True)
                logging.info(f"Encoding of {source} done.")
                logging.info(
                    f"Size of output file: {sizeConvertion(os.path.getsize(output_path))} MiB "
                )
                if self.remove_file:
                    self.delete_file(source.split(os.sep)[-1])

                logging.info(f"Encoding of {source} done.")
                logging.info(
                    f"Size of output file: {sizeConvertion(os.path.getsize(output_path))} MiB "
                )
                if self.remove_file:
                    self.delete_file(source.split(os.sep)[-1])
                logging.info(
                    f"Encoding of {source} completed."
                )
                mail(source, nomail=self.no_mail)
            except ffmpeg.Error as e:
                ffmpeg_err = e.stderr.decode("utf-8", errors="replace") if e.stderr else "No stderr output"
                logging.error(f"FFmpeg error on {source}:\n{ffmpeg_err}")
                mail(source, error=ffmpeg_err[-3000:], nomail=self.no_mail)
                exit()    
        except Exception as e:
            exc_tb = sys.exc_info()[2]
            error_message = f'{e}\nError occured in function encode_file, Line: {exc_tb.tb_lineno}'
            logging.error(error_message)
            mail(source, error=error_message, nomail=self.no_mail)

    def encode_files(self) -> None:
        files = [f for f in os.listdir(self.source) if any(f.lower().endswith(ext) for ext in extensions)]
        files_count = len(files)
        processed_files = 0
        self.no_mail = True
        remove = input("Delete files after encode completion? (y/n): ").lower()

        for original in files:
            self.encode_file(source = os.path.join(self.source, original), remove=remove)
            processed_files += 1
            logging.info(
                f"Encoding Progress: {processed_files}/{files_count} files processed."
            )
                        
        mail(self.source)

def mail(sDir, **kwargs) -> None:
    if kwargs.get("nomail"):
        return
    smail = os.environ.get('source_mail')
    passwd = os.environ.get('password') # changed the password I accidentally left here.
    rmail = os.environ.get('receiver')

    subject = f"Encoding Progress of {sDir}"
    message = f"Encoding of {sDir} has been finished."

    error = kwargs.get("error", None)

    if kwargs.get("error"):
        subject = f"{subject} : ERROR"
        message = (
            f"An Error occured during the encoding. \nError: {kwargs.get('error')}"
        )

    pText = f"Subject:{subject}\n\n{message}"
    with smtplib.SMTP("smtp.gmail.com", 587) as server:
        server.starttls()
        server.login(smail, passwd)

        server.sendmail(smail, rmail, pText)

        print(f"Email has been sent to {rmail}")

    if error:
        exit()


def delete_dir(source) -> None:
    screens = [ 
        ["screens"],
        ['screen'],
        ['Screen'],
        ['Screens'],
        ['_screen'],
        ['_screens'],
        ['_Screens'],
        ['_Screen']
    ]
    if any(os.listdir(source) == dirSt for dirSt in screens): # this check if the only subdir in the directory is a screen directory
        for root, dirs, files in os.walk(source):
            if root != source:
                for fil in files:
                    os.remove(os.path.join(root, fil))
                for d in dirs:
                    for r, sd, fs in os.walk(os.path.join(root, d)):
                        for f in fs:
                            os.remove(os.path.join(root,f))
                        os.rmdir(r)
                os.rmdir(root)

            
        logging.info(f"{source}'s screens directory deleted successfully.")
    else:
        logging.info(f"{source} has subdirectories other than screens. Please check them out.")
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
        error_message = f'{e} (Error Code Line:{exc_tb.tb_lineno})'
        logging.error(error_message)
        mail(encoder.source, error=error_message, nomail=encoder.no_mail)


if __name__ == "__main__":
    main()