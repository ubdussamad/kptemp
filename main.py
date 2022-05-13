from imp import find_module
from typing import Dict, Set, List
from essence import *
import pickle
import os
import json
import re
from utils import *
import subprocess

# TODO:
# * We're still depending upon no kaslr, remove the need for it.
# * Make generation more efficient.

KPATCH_BINARY_PATH = "kpatch/kpatch-build/kpatch-build"

NUMBER_OF_CONCURRENT_MAKE_JOBS = 28

WORKLOAD_PATH: str = "/home/samad/lp_test/dummy-workload.sh"
VMLINUX_PATH: str = "vmlinux"

KPATCH_SRC_DIR_TREE = "linux-4.9.31/"
KPATCH_SRC_MOD_DIR_TREE = "linux-4.9.31-mod/"

SOURCE_PARSER_LINUX_TREE: str = "build/linux-4.9.31/"
SOURCE_TREE_FILE_ENCODING: str = "iso-8859-1"
# KERNEL_DEBUG_BINARY_LINUX_TREE: str = Binutils.find_build_root(VMLINUX_PATH) # The path in which the kernel binary was built.


DEP_SOLVER_LINUX_TREE: str = "linux-4.9.31/"
DEP_SOLVER_KERNEL_VERSION: str = "4.19.231"
DEP_SOLVER_GCC_VERSION_TEXT: str = "gcc (Ubuntu 7.5.0-3ubuntu1~18.04) 7.5.0" # GCC version of your compiler.

def setup_environment() -> None:
    # Environment Variables used for kconfiglib. Edit them as you may deem fit.
    os.environ["srctree"] = DEP_SOLVER_LINUX_TREE
    os.environ["ARCH"] = "x86"
    os.environ["SRCARCH"] = "x86"
    os.environ["KERNELVERSION"] = DEP_SOLVER_KERNEL_VERSION
    os.environ["CC"] = "gcc"
    os.environ["HOSTCC"] = "gcc"
    os.environ["HOSTCXX"] = "g++"
    os.environ["CC_VERSION_TEXT"] = DEP_SOLVER_GCC_VERSION_TEXT
    os.environ["LD"] = "ld"

def trace_kernel() -> List[str]:
    # Tracing the kernel source here.
    if not os.path.exists(".tracercache"):
        t = tracer.FtraceTracer(VMLINUX_PATH)
        s = t.trace(WORKLOAD_PATH)
        print("Workload has Finished running.")
        sources = list(t.addrs_to_kernel_source_lines(s))

        with open(".tracercache", "wb") as fobj:
            pickle.dump(sources, fobj)
    else:
        print("Using prebuilt tracer cache.")
        with open(".tracercache", "rb") as fobj:
            sources = pickle.load(fobj)
    print(f"Length of source file array is: {len(sources)}")
    return sources

def parse_source(sources):
    p = parser.LinuxParser(SOURCE_PARSER_LINUX_TREE)
    # Parsing the source for configs, etc.
    print("Parsing kernel source......")
    if not os.path.exists(".parsercache"):
        print("Building cache...")
        p.parse()
        p.parse_c_files_for_configs()

        with open(".parsercache", "wb") as fobj:
            pickle.dump(p, fobj)
        print('Done building parser cache.')
    else:
        print("Using prebuilt parser cache, Done.")
        with open(".parsercache", "rb") as fobj:
            p = pickle.load(fobj)

    # Module Tracing and config generation. The workload should write the content of of /proc/modules.
    # TODO: Make the framework do this not the workload. Maybe take random samples during runtime.
    modules = None
    with open("modules", "r") as fobj:
        modules = fobj.read()
    modules = [f"{i.split(' ')[0]}" for i in modules.split("\n") if i]
    config_mods = set()
    for filename in p.makefile_config_map.keys():
        for module_name in modules:
            if module_name in filename.split("/")[-1]:
                config_mods.update(p.makefile_config_map[filename])
    print(f"Configs genarted from mods: {len(config_mods)} \n")

    # Genrating the configs from traced source files
    configs_src = []
    for traced_source_line in sources:
        _fpath,_linum = traced_source_line.split(':')
        _fpath = _fpath[len(KERNEL_DEBUG_BINARY_LINUX_TREE):]
        _fpath = os.path.abspath(SOURCE_PARSER_LINUX_TREE.rstrip('/') + _fpath)
        k = p.query(_fpath, int(_linum) if _linum.isdigit() else None)
        configs_src.append(k)

    configs_src = [i for i in configs_src if i]
    print(f"Length of configs genrated from traced functions after filtering are: {len(configs_src)}.")

    # Combining configs from LKMs and Source trace.
    for i in configs_src:
        for j in i:
            config_mods.add(j)
    print(
        f"Total unique configs genarted after combining modules and traced functions: {len(config_mods)}"
    )

    return config_mods, p.config_to_c_file_map

def get_current_build_configs():
    # Getting the current set of configs with which the current kernel is built.
    with open(f"/boot/config-{os.uname().release}") as f:
        config = f.read()
        build_configs = re.findall(r"\n(CONFIG_[A-Z,0-9,_,-]+)=(?:y|m)", config)
        return build_configs

def get_src_files_from_configs(unused_configs, config_to_c_file_map):
    # Inefficiently figuring out the source file names with contains those specific configs.
    unused_configs_to_file_map: Dict[str, Set[str]] = {i: set() for i in unused_configs}
    for i in unused_configs:
        try:
            for file in config_to_c_file_map[i]:
                unused_configs_to_file_map[i].add(file)
        except:
            pass

    for i in unused_configs_to_file_map.copy().keys():
        if not len(unused_configs_to_file_map[i]):
            unused_configs_to_file_map.pop(i, None)
    return unused_configs_to_file_map

def fish_function_defs_under_configs(unused_configs_to_file_map):
    funcs = set()
    prog = ProgressCounter("\nFunction capture",len(unused_configs_to_file_map.keys()),1)

    config_file_func_map : Dict[ str , Dict [ str , Set[str] ]] = dict()
    
    for config in unused_configs_to_file_map.keys():
        prog.update()
        files = unused_configs_to_file_map[config]

        for file in files:
            # Here we check for a function definition and it's call within the config block of the file.
            # If there is a function which is defined and called within a same config, we register it for patching.
            if file[-2:] == ".h":continue
            with open(file, "r", encoding=SOURCE_TREE_FILE_ENCODING) as f:
                source = f.read()
                xc = r"#ifdef\s+"+config+r".+?#endif"
                configs = re.findall(xc, source, re.M | re.DOTALL)
                string_under_config = "".join(configs)
                function_defs = re.findall(
                    r"^(?:[a-z,0-9,_,-]+\s)+([a-z,0-9,_,-]+\s*\()",
                    string_under_config,
                    re.M,
                )
                for func in function_defs:
                    # Some filtering
                    if 'notrace' in func or func.startswith('_'):
                        continue
                    try:
                        _tmp = config_file_func_map[config]
                        try:
                            _tmp[file].append(func)
                        except:
                            _tmp[file] = [func,]
                    except:
                        config_file_func_map[config] = {file : [func,]}
    
    return config_file_func_map

def check_tokens_in_str(string, itr = ['static','void','int','float','double','u32',]):
    # The function which can't be traced can't be patched.
    if 'notrace' in string:
        return False
    for i in ['if ', ' if(', 'do ', 'do {', '__init']:
        if i in string:
            print(f"Skipping line: {string}")
            return False
    for i in itr:
        if i in string:return True
    return False

def find_balance(string, bracket='curly'):
    if bracket == 'curly':return string.count('{') - string.count('}')
    elif bracket == 'round':return string.count('(') - string.count(')')
    else:
        raise TypeError("Unknow Bracket type. Choose curly or round.")

def find_function_linums(final_map:dict,):
    _tree = dict()
    _src_parser_tree_abs = len( os.path.abspath(SOURCE_PARSER_LINUX_TREE) )

    for config in list(final_map.keys()):
        
        _tree[config] = dict()
        
        for file in final_map[config]:
            
            _genric_file_name = '[kernel_tree_root]/'+file[_src_parser_tree_abs:].lstrip('/')
            _tree[config][ _genric_file_name ] = dict()
            
            with open(file, 'r', encoding=SOURCE_TREE_FILE_ENCODING) as f:
                raw = f.read()

                for function in final_map[config][file]:
                    
                    k = raw.split('\n')
                    function_found = False
                    balance = 0
                    primary_found = False
                    initial_linum = -1
                    
                    for linum, i in enumerate(k):
                        
                        if function_found and balance > 0:
                            primary_found = True

                        if function_found:
                            balance += find_balance(i)
                            if primary_found and balance == 0:
                                fname = os.path.abspath("linux-4.9.31-mod"+file[len('/home/samad/lp_test/build/linux-4.9.31'):])

                                _tree[config][ _genric_file_name ][function] = {
                                'start_linum': initial_linum + 1,
                                'end_linum': linum + 1,
                                }

                                break
                            continue
                        
                        if function in i and check_tokens_in_str(i):
                            balance += find_balance(i)
                            initial_linum = linum
                            function_found = True
    return _tree

def genrate_patch(tree, kp_mod_directory_tree , kp_src_dir_tree):
    
    try:os.makedirs('kpatch-diffs/')
    except Exception as err:print(f"Dir already created or {err}")

    with open('kpatch-diffs/tree.json' , 'w') as fobj:
        __result = json.dumps(tree, indent = 2)
        fobj.write(__result)

    prompt = True
    print(f"Ask before genrating patch for each config (y/n):", end='')
    choice = input("")
    if choice == 'n':
        prompt = False

    # prog = ProgressCounter("\nPatch Creation",len(tree.keys()),1)

    for config in tree.keys():
        # prog.update()
        if prompt:print(f"\nCreate Patch for {config} (y/n):", end='')
        if prompt:choice = input("")

        if prompt:        
            if choice == 'n':
                print(f"Skipping Patch for config {config}.")
                continue
            else:
                print(f"Genrating patch for config {config}.")
        if not prompt:print("Trying to building monolithic patch for config: {config}: " , end='')
        # Genrate the diffs for each file under the config.
        for filename in tree[config].keys():
            _actual_filename = filename.replace( '[kernel_tree_root]' , kp_mod_directory_tree.rstrip('/'))
            _actual_non_mod_filename = filename.replace( '[kernel_tree_root]' , kp_src_dir_tree.rstrip('/'))
            _clean_file = filename.replace( '[kernel_tree_root]' , "tmp/linux-4.9.31")

            with open(_clean_file,'r') as forig:
                __text = forig.read()
                __file = __text.split('\n')
                original_line_count  = len(__file)
            with open(_actual_filename,'w') as f_mod:f_mod.write(__text)
            with open(_actual_non_mod_filename,'w') as f_mod:f_mod.write(__text)


            
            for function in tree[config][filename].keys():

                with open(_actual_filename) as fobj:file = fobj.read().split('\n')
                _current_line_count  = len(file)
                
                # Since while replacing stuff, this code can only increse line count (of the file) and not decrease it.
                start_linum = tree[config][filename][function]['start_linum'] + _current_line_count - original_line_count
                end_linum = tree[config][filename][function]['end_linum'] + _current_line_count - original_line_count

                if prompt:print(f"{_actual_filename}:{start_linum}")
                
                k = '\n\n'
                for i in range(start_linum-1, end_linum):
                    ql = file[i]
                    k += ql
                    file[i] = ''
                
                ptr = r'\{.*\}' # The DOT is greedy on purpose.
                
                k = re.sub(  ptr  , '{\n}' , k  , re.DOTALL)

                file[start_linum] = k

                with open(_actual_filename, 'w') as f:f.write( '\n'.join(file) )
            
            o = f"diff -u {_actual_non_mod_filename} {_actual_filename} > kpatch-diffs/{config}-{filename.split('/')[-1]}.patch"
            diff = subprocess.call(
                o,
                shell=True,
                )

        # Run all patched files under the config with kpatch.
        # print(f'CMDLINE: {KPATCH_BINARY_PATH} -t vmlinux -v {VMLINUX_PATH} -R --skip-compiler-check -s {KPATCH_SRC_DIR_TREE} -j {NUMBER_OF_CONCURRENT_MAKE_JOBS} -o kpatch_objects/ -n {config}-all.ko kpatch-diffs/{config}-*')
        ret_code = subprocess.call(
            [f'{KPATCH_BINARY_PATH} -t vmlinux -v {VMLINUX_PATH} -R --skip-compiler-check -s {KPATCH_SRC_DIR_TREE} -j {NUMBER_OF_CONCURRENT_MAKE_JOBS} -o kpatch_objects/ -n {config}-all.ko kpatch-diffs/{config}-*',],
            shell = True,
            stdout=open('/dev/null' , 'w'),
            stderr=open('/dev/null' , 'w'),
        )

        # Building all the file togather fail
        if ret_code != 0:
            print(f"Failed")
            # print(f"Files are: \n {tree[config].keys()}\n")
            # input("Go?: ")
            # Try building for each file separately.
            for filename in tree[config].keys():
                print(f"Trying creating a patch for {filename} under the config {config} : " , end='')
                patch = f"kpatch-diffs/{config}-{filename.split('/')[-1]}.patch"
                cmx = f'{KPATCH_BINARY_PATH} -t vmlinux -v {VMLINUX_PATH} -R --skip-compiler-check -s {KPATCH_SRC_DIR_TREE} -j {NUMBER_OF_CONCURRENT_MAKE_JOBS} -o kpatch_objects/ -n {config}-split-{filename}.ko {patch}'
                print(f"CMDLINE: \n\n {cmx} \n")
                ret_code = subprocess.call(
                [f'{KPATCH_BINARY_PATH} -t vmlinux -v {VMLINUX_PATH} -R --skip-compiler-check -s {KPATCH_SRC_DIR_TREE} -j {NUMBER_OF_CONCURRENT_MAKE_JOBS} -o kpatch_objects/ -n {config}-split-{filename}.ko {patch}'],
                shell = True,
                stdout=open('/dev/null' , 'w'),
                stderr=open('/dev/null' , 'w'),
                )
                if ret_code:print("Failed")
                else: print("Success.")
        else:
            print(f"Sucess!")

        for file in tree[config].keys():
            _actual_filename = file.replace( '[kernel_tree_root]' , kp_mod_directory_tree.rstrip('/'))
            _actual_non_mod_filename = file.replace( '[kernel_tree_root]' , kp_src_dir_tree.rstrip('/'))

            _clean_file = file.replace( '[kernel_tree_root]' , "tmp/linux-4.9.31")

            with open(_clean_file,'r') as forig:
                __text = forig.read()
                __file = __text.split('\n')
                original_line_count  = len(__file)
            with open(_actual_filename,'w') as f_mod:f_mod.write(__text)
            with open(_actual_non_mod_filename,'w') as f_mod:f_mod.write(__text)

            os.remove(f"kpatch-diffs/{config}-{file.split('/')[-1]}.patch")
            # print("Removed the mod and the patch.")



if __name__ == "__main__":
    # setup_environment()
    
    # dep_solver = kconfDepSolver()

    # traced_sources = trace_kernel()

    # configs,config_to_c_file_map = parse_source(traced_sources)

    # final_dep_solved_configs = dep_solver.solve_dependencies(configs)

    # print(f"Total configs genrated after dependency resolution is: {len(final_dep_solved_configs)}")

    # build_configs = get_current_build_configs()

    # Taking the diffrence of two sets.
    # unused_configs = [i for i in build_configs if i not in final_dep_solved_configs]

    # unused_configs_to_file_map = get_src_files_from_configs(unused_configs, config_to_c_file_map)

    # final_map = fish_function_defs_under_configs(unused_configs_to_file_map)

    # _tree = find_function_linums(final_map)
    
    # original_dir_name = "linux-4.9.31"
    t = json.load(open('tree.json'))
    genrate_patch( t, KPATCH_SRC_MOD_DIR_TREE, KPATCH_SRC_DIR_TREE)
