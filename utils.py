
def colored(r, g, b, text):
    return "\033[38;2;{};{};{}m{}\033[38;2;255;255;255m".format(r, g, b, text)


class ProgressCounter:
    def __init__(
            self,
            string: str,
            max_count: int,
            precision_digits: int = 2,
            flush: bool = True
        ):
        """
        Class for handling progress counting.

        Uses simple formula to calculate progress:
            percentage = (internal_count * 100 / max_count)
            where 0 =< internal_count < max_count

        Usage:
        * Initialize the class by providing init arguments.
        * Update Progress by calling the object.update() method.

        Note:

        Don't write anything to stdout (using print or otherwise) while you're updating progress.
        e.g No print statements between class initialization and update. Until the progress has finished.

        Args:
        string : type<str>, A string describing whats is happening. e.g Searching, Loading, etc.
        NOTE: The colon will be added by the class, just provide what's  happening in the string.
        e.g string = Searching
        Output: Searching progress: 50.00%

        maxcount : type<int>, The upper limit for progress percentage calculation. (The denominator.)

        precision_digits : type<int>, Number of precision to display while displaying the percentage. (Default 2 Digits)

        flush : type<bool>, Flush the progress to the stdout everytime an update is made. (Default True)

        Methods:

        Progresscounter.update()
        Updates the progress and reflects that on stdout.

        Args:
        count : type<int>, Number of counts the progress should be increased to. (Default 1)
        """
        self.string:str = string
        self.max_count:int = max_count
        self.precision_digits:int = precision_digits
        self.flush:bool = flush
        self.progress_count:int = 0
        self._num_digits = 0

        self._start()

    def _start(self):
        print(
            f"{self.string} progress: {self.progress_count * 100 / self.max_count:.{self.precision_digits}f}%",
            flush = self.flush,
            end = '',
        )
    
    def update(self, count: int = 1):
        """
        Updates the progress and reflects that on stdout.

        Args:
        count : type<int>, Number of counts the progress should be increased to. (Default 1)
        """
        if self.max_count - self.progress_count < 1:
            print("Can't update, max count exceeded!")
            return
        
        _length_of_progress_string = len(f"{self.progress_count * 100 / self.max_count:.{self.precision_digits}f}%")
        self.progress_count += count

        # Going back to start of the progress counter string.
        print("\b" * _length_of_progress_string, flush=self.flush, end = '')

        _current_progress_percentage = self.progress_count * 100 / self.max_count

        print(
            f"{_current_progress_percentage:.{self.precision_digits}f}%",
            flush = self.flush,
            end = '',
        )
        
        if _current_progress_percentage > 99.99:
            print('', flush = self.flush)


import os

class progressTracker:
    def __init__ (self,logFile):
        self.logfile = logFile
        self.config_list = []

        if os.path.exists(self.logfile):
            with open(self.logfile) as f:
                self.raw_file_txt = f.read()
                self.config_list = [config for config in self.raw_file_txt.split('\n') if config]
        
        else:
            with open(logFile, 'w') as f:f.write('\n')
    
    def check(self, config):
        if config in self.config_list:
            return True
        else:
            # Add the config to the file.
            self.config_list.append(config)
            self._flush()
            return False
    
    def _flush(self):
        with open(self.logfile , 'w') as f:
            f.write(
                '\n'.join(self.config_list)
            )

