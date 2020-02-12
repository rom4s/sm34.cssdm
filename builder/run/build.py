# coding=utf8

import os, sys
import argparse, subprocess, requests, json
import distutils.dir_util as dirutil
from uritemplate import URITemplate

requests.packages.urllib3.disable_warnings()

args = argparse.ArgumentParser()
args.add_argument('-cc', type=str)
args.add_argument('-cxx', type=str)
args.add_argument('-o', type=str)
args.add_argument('--mms-path', type=str)
args.add_argument('--sm-path', type=str)
args.add_argument('--sm-bin-path', type=str)
args.add_argument('--hl2sdk-ep1', type=str)
args.add_argument('--no-update-script', type=str)
args = args.parse_args()

class CBuilder:
    def __init__(self):
        global args
        self.args = args

        self.script_dir = os.path.dirname(os.path.abspath(__file__))
        self.patches_dir = os.path.realpath(os.path.join(self.script_dir, '..', 'patches'))
        self.source_dir = os.getcwd()
        self.release_uploads = {}

        self.OUT = args.o or os.path.realpath(os.path.join(self.source_dir, '..', 'OUT'))
        self.SUPPRESS_OUTPUT = '>nul 2>&1' if sys.platform.startswith('win') else '>/dev/null 2>&1'
        self.SAVE_OUTPUT = 'powershell "{0} |& tee build.log"' if sys.platform.startswith('win') else '{0} |& tee build.log'

        self.init()
        self.config()
        # self.update()
        self.patch()
        self.bootstrap()
        self.build()
        self.package()

    def init(self):
        version_file = os.path.join(self.source_dir, 'product.version')
        try:
            with open(version_file, 'r') as hFile:
                self.src_version = hFile.readline().strip().split('-')[0]
                self.src_branch = '.'.join(self.src_version.split('.')[:2])
        except IOError as e:
            raise Exception('[Init] Error reading file: {0}'.format(version_file))

        self.src_commit = int(subprocess.check_output('git rev-list --count HEAD', shell=True).decode().strip())
        self.src_revision = subprocess.check_output('git rev-parse HEAD', shell=True).decode().strip()

        os.chdir('..')
        try:
            self.build_commit = subprocess.check_output('git rev-parse HEAD', shell=True).decode().strip()
        except:
            self.build_commit = 'master'
        os.chdir(self.source_dir)

    def config(self):
        config_file = os.path.join(self.script_dir, 'config.json')
        try:
            with open(config_file, 'r') as hFile:
                config = json.load(hFile)
        except IOError as e:
            raise Exception('[Config] Error reading file: {0}'.format(config_file))

        if not self.src_branch in config:
            raise Exception('[Config] Couldn\'t find branch <{0}> in {1}'.format(self.src_branch, config_file))

        commit_selected = 0
        commit_patch = ''
        for commit_id, commit_config in config[self.src_branch].items():
            commit_id = int(commit_id)
            if self.src_commit < commit_id or commit_id < commit_selected:
                continue

            commit_patch = os.path.join(self.patches_dir, self.src_branch, commit_config['patch'])
            if not os.path.isfile(commit_patch):
                print('[Config] Not exists patch <{0}#{1}> ({2})'.format(self.src_branch, commit_id, commit_patch))
                continue
            commit_selected = commit_id

        if commit_selected == 0:
            raise Exception('[Config] Couldn\'t find config for <{0}#{1}>'.format(self.src_branch, self.src_commit))

        print('[Config] Selected config for <{1}#{0}> is <{1}#{2}>'.format(self.src_commit, self.src_branch, commit_selected))
        self.config = config[self.src_branch][str(commit_selected)]
        self.config['patch'] = commit_patch

    def update(self):
        # if(self.args.)
        print('[Update] Attempting to update...')

        os.chdir(script_dir)
        try:
            subprocess.check_call('git pull --rebase origin master', shell=True)
            print('[Update] Successfully updated')
        except:
            print('[Update] Failed to update builder')
        os.chdir(sourcemod_dir)

    def patch(self):
        os.chdir(self.source_dir)
        print('[Patch] Attempting to patching...')

        try:
            subprocess.check_call('git reset --hard', shell=True)
            subprocess.check_call('git submodule update --init --recursive -f', shell=True)
            subprocess.check_call('git apply --ignore-space-change --ignore-whitespace {0} {1}'.format(self.config['patch'], self.SUPPRESS_OUTPUT), shell=True)
        except:
            raise Exception('[Patch] Failed to patching')

        print('[Patch] Successfully patched')

    def bootstrap(self):
        print('[Bootstrap] Attempting to reconfigure...')

        self.env = os.environ.copy()

        conf_argv = [
            '--enable-optimize',
            # '--no-color',
        ]

        if args.mms_path:
            self.env['MMSOURCE110'] = args.mms_path
        if args.sm_path:
            self.env['SOURCEMOD110'] = args.sm_path
        if args.sm_bin_path:
            self.env['SOURCEMOD_BIN'] = args.sm_bin_path
        if args.hl2sdk_ep1:
            self.env['HL2SDKEP1'] = args.hl2sdk_ep1

        conf_argv = ' '.join(conf_argv)
        command = ('' if sys.platform.startswith('win') else 'CC={0} CXX={1} '.format(args.cc or self.config['CC'], args.cxx or self.config['CXX'])) + 'python {0} {1}'.format(os.path.join(self.source_dir, 'configure.py'), conf_argv)

        try:
            os.mkdir(self.OUT)
        except Exception:
            pass
        os.chdir(self.OUT)

        try:
            subprocess.check_call(command, shell=True, env=self.env)
        except:
            raise Exception('[Bootstrap] Could not configure')

        print('[Bootstrap] Configured')

    def build(self):
        print('[Build] Start')

        try:
            subprocess.check_call('python build.py', shell=True, env=self.env)
        except:
            raise Exception('[Build] Failed')

        self.build_strip_debug()

    def build_strip_debug(self):
        if sys.platform.startswith('win'):
            return

        print('[Objcopy] Stripping debug...')
        for dirname, subdirs, files in os.walk('package/addons'):
            subdirs.sort()
            files.sort()
            for filen in files:
                if filen[-3:] == '.so':
                    subprocess.check_call('objcopy --strip-debug {0}'.format(os.path.join(dirname, filen)), shell=True)
                    print(os.path.join(dirname, filen))

    def package(self):
        import zipfile, tarfile, gzip
        import shutil, re
        from io import StringIO, BytesIO
        from time import localtime, time

        gamedata_w = ()

        os.chdir('package')

        gamedata_dir_in = os.path.join(self.patches_dir, self.src_branch, 'gamedata')
        if os.path.isdir(gamedata_dir_in):
            gamedata_dir_out = os.path.join('addons', 'sourcemod', 'gamedata')

            print('[Package] Copying gamedata...')
            dirutil.remove_tree(gamedata_dir_out)
            dirutil.copy_tree(gamedata_dir_in, gamedata_dir_out, preserve_times=0)

            for filename in gamedata_w:
                try:
                    shutil.copy(os.path.join(self.source_dir, 'gamedata', filename), os.path.join('addons', 'sourcemod', 'gamedata', filename))
                except:
                    pass

        output = 'cssdm-{0}-git{1}-css34-'.format(self.src_version, self.src_commit)
        print('[Package] Output file: {0}'.format(output))

        in_archive = ('addons', 'cfg')
        func = None

        if sys.platform.startswith('linux'):
            output = output + 'linux.tar.gz' 
            print('tar zcvf {0} {1}'.format(output, ' '.join(in_archive)))
            archive = tarfile.open(output, 'w:gz')
            func = archive.add
        elif sys.platform.startswith('win'):
            output = output + 'windows.zip'
            print('zip -r {0} {1}'.format(output, ' '.join(in_archive)))
            archive = zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED)
            func = archive.write
        else:
            output = output + 'mac.zip'
            print('zip -r {0} {1}'.format(output, ' '.join(in_archive)))
            archive = zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED)
            func = archive.write

        for f in in_archive:
            for dirname, subdirs, files in os.walk(f):
                subdirs.sort()
                files.sort()

                try:
                    func(dirname + os.sep, recursive=False)
                except:
                    try:
                        func(dirname + os.sep)
                    except:
                        pass

                print(dirname + os.sep)
                for filename in files:
                    func(os.path.join(dirname, filename))
                    print(os.path.join(dirname, filename))
        archive.close()

        self.upload_github(output)
        self.upload_bitbucket(output)
        self.discord_notify()

        print('{0}{1} -- build succeeded.'.format('File sent to drop site as ' if self.release_uploads else '', output))

    def upload_github(self, out_archive):
        variables = ('GITHUB_LOGIN', 'GITHUB_TOKEN', 'GITHUB_API_PATH')
        for var in variables:
            if var not in os.environ:
                print('[Upload:GitHub] Not found required variable <{0}> in environment. SKIP!'.format(var))
                return

        headers = {'Accept': 'application/vnd.github.v3+json'}
        auth = (os.environ['GITHUB_LOGIN'], os.environ['GITHUB_TOKEN'])

        # create release
        print('[Upload:GitHub] Creating a release...')
        response = requests.post('{0}/releases'.format(os.environ['GITHUB_API_PATH']), auth=auth, headers=headers, json={
            'tag_name': 'v{0}.{1}'.format(self.src_version, self.src_commit),
            'target_commitish': self.build_commit,
            'name': 'Build v{0}.{1}'.format(self.src_version, self.src_commit),
            'body': 'Build artifacts',
        })

        try:
            response = response.json()
            if response['errors'][0]['code'] == 'already_exists':
                # get release
                print('[Upload:GitHub] Release already exists. Get a release!')
                response = requests.get('{0}/releases/tags/v{1}.{2}'.format(os.environ['GITHUB_API_PATH'], self.src_version, self.src_commit), auth=auth, headers=headers).json()
            else:
                print('[Upload:GitHub] FAILED to create a release! ({0})'.format(response['errors'][0]['code']))
                return
        except:
            if 'message' in response:
                print('[Upload:GitHub] FAILED to create a release! ({0} - {1})'.format(response['message'], response['documentation_url']))
                return
            print('[Upload:GitHub] Success created a release.')
            pass

        # check upload_url exists
        try:
            response['upload_url']
        except:
            print('[Upload:GitHub] FAILED to get response[upload_url]!')
            return

        file_from = os.path.join(self.OUT, 'package', out_archive)
        file_to = URITemplate(response['upload_url']).expand(name=out_archive)

        # upload release asset
        print('[Upload:GitHub] Trying to upload release asset...')
        try:
            with open(file_from, 'rb') as f:
                response = requests.post(file_to, data=f, auth=auth, headers={'Content-Type': 'application/octet-stream'}).json()
        except:
            print('[Upload:GitHub] FAILED to upload release asset. SKIP!')
            return

        print('[Upload:GitHub] Success upload release asset.')
        self.release_uploads['GitHub'] = response['browser_download_url']

    def upload_bitbucket(self, out_archive):
        variables = ('BITBUCKET_LOGIN', 'BITBUCKET_TOKEN', 'BITBUCKET_API_PATH')
        for var in variables:
            if var not in os.environ:
                print('[Upload:BitBucket] Not found required variable <{0}> in environment. SKIP!'.format(var))
                return

        headers = {'Accept': 'application/json'}
        auth = (os.environ['BITBUCKET_LOGIN'], os.environ['BITBUCKET_TOKEN'])
        api_path =  URITemplate(os.environ['BITBUCKET_API_PATH']).expand(src_branch=self.src_branch)
        repo_created = True

        request = {'scm': 'git'}
        if 'BITBUCKET_PROJECT' in os.environ:
            request['project'] = {'key': os.environ['BITBUCKET_PROJECT']}


        # create repository if not exists
        response = requests.post(api_path, auth=auth, headers=headers, json=request)
        try:
            response = response.json()
            if response['error']['message'] != 'Repository with this Slug and Owner already exists.':
                repo_created = False
        except:
            repo_created = False

        if not repo_created:
            print('[Upload:Bitbucket] FAILED to create repository (status: {0}). SKIP!'.format(response.status_code))
            return

        file_from = os.path.join(self.OUT, 'package', out_archive)

        # upload release asset
        print('[Upload:Bitbucket] Trying to upload release asset...')
        try:
            with open(file_from, 'rb') as f:
                response = requests.post('{0}/downloads'.format(api_path), files={'files': f}, auth=auth)
        except:
            print('[Upload:Bitbucket] FAILED to upload release asset. SKIP!')
            return

        if response.status_code != 201:
            print('[Upload:Bitbucket] FAILED to upload release asset (status: {0}). SKIP!'.format(response.status_code))
            return

        self.release_uploads['Bitbucket'] = '{0}/downloads/{1}'.format(api_path.replace('https://api.bitbucket.org/2.0/repositories/', 'https://bitbucket.org/'), out_archive)

        print('[Upload:Bitbucket] Success upload release asset.')

    def discord_notify(self):
        if 'DISCORD_WEBHOOK' not in os.environ:
            print('[Discord] Not found required variable <{0}> in environment. SKIP!'.format('DISCORD_WEBHOOK'))
            return

        if not self.release_uploads:
            print('[Discord] Not found uploaded releases. SKIP!'.format(var))

        from discord_webhook import DiscordWebhook, DiscordEmbed

        if sys.platform.startswith('win'):
            _os = 'Windows'
            _color = 0x0F3674
        elif sys.platform.startswith('linux'):
            _os = 'Linux'
            _color = 0x20BF55
        else:
            _os = 'MacOS'
            _color = 0x31393C

        webhook = DiscordWebhook(url=os.environ['DISCORD_WEBHOOK'])
        embed = DiscordEmbed(title='[{2}] CSS:DM Build {0}.{1}'.format(self.src_version, self.src_commit, _os), description='CSS:DM Build {0}.{1} available for download.'.format(self.src_version, self.src_commit), color=_color)

        for name, value in self.release_uploads.items():
            embed.add_embed_field(name=name, value=value)

        webhook.add_embed(embed)
        response = webhook.execute()

# run
CBuilder()