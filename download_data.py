import subprocess
import argparse
import os

parser = argparse.ArgumentParser(description='Download celebA-HQ helper')
parser.add_argument('dataset', type=str)
parser.add_argument('path', type=str)

if __name__ == '__main__':
    args = parser.parse_args()
    dataset = args.dataset
    dirpath = args.path

    global_data_dir = os.path.join(dirpath, dataset)
    os.makedirs(global_data_dir, exist_ok=True)

    if dataset == 'celeba':
        filenames = [
            'img_celeba.7z.001', 'img_celeba.7z.002', 'img_celeba.7z.003', 
            'img_celeba.7z.004', 'img_celeba.7z.005', 'img_celeba.7z.006', 
            'img_celeba.7z.007', 'img_celeba.7z.008', 'img_celeba.7z.009', 
            'img_celeba.7z.010', 'img_celeba.7z.011', 'img_celeba.7z.012', 
            'img_celeba.7z.013', 'img_celeba.7z.014',
        ]
        drive_ids = [
            '0B7EVK8r0v71pQy1YUGtHeUM2dUE', '0B7EVK8r0v71peFphOHpxODd5SjQ',
            '0B7EVK8r0v71pMk5FeXRlOXcxVVU', '0B7EVK8r0v71peXc4WldxZGFUbk0',
            '0B7EVK8r0v71pMktaV1hjZUJhLWM', '0B7EVK8r0v71pbWFfbGRDOVZxOUU',
            '0B7EVK8r0v71pQlZrOENSOUhkQ3c', '0B7EVK8r0v71pLVltX2F6dzVwT0E',
            '0B7EVK8r0v71pVlg5SmtLa1ZiU0k', '0B7EVK8r0v71pa09rcFF4THRmSFU',
            '0B7EVK8r0v71pNU9BZVBEMF9KN28', '0B7EVK8r0v71pTVd3R2NpQ0FHaGM',
            '0B7EVK8r0v71paXBad2lfSzlzSlk', '0B7EVK8r0v71pcTFwT1VFZzkzZk0',
        ]
    elif dataset == 'celeba-hq':
        filenames = [
            'deltas00000.zip', 'deltas01000.zip', 'deltas02000.zip',
            'deltas03000.zip', 'deltas04000.zip', 'deltas05000.zip',
            'deltas06000.zip', 'deltas07000.zip', 'deltas08000.zip',
            'deltas09000.zip', 'deltas10000.zip', 'deltas11000.zip',
            'deltas12000.zip', 'deltas13000.zip', 'deltas14000.zip',
            'deltas15000.zip', 'deltas16000.zip', 'deltas17000.zip',
            'deltas18000.zip', 'deltas19000.zip', 'deltas20000.zip',
            'deltas21000.zip', 'deltas22000.zip', 'deltas23000.zip',
            'deltas24000.zip', 'deltas25000.zip', 'deltas26000.zip',
            'deltas27000.zip', 'deltas28000.zip', 'deltas29000.zip',
        ]
        drive_ids = [
            '0B4qLcYyJmiz0TXdaTExNcW03ejA', '0B4qLcYyJmiz0TjAwOTRBVmRKRzQ',
            '0B4qLcYyJmiz0TjNRV2dUamd0bEU', '0B4qLcYyJmiz0TjRWUXVvM3hZZE0',
            '0B4qLcYyJmiz0TjRxVkZ1NGxHTXc', '0B4qLcYyJmiz0TjRzeWlhLVJIYk0',
            '0B4qLcYyJmiz0TjVkYkF4dTJRNUk', '0B4qLcYyJmiz0TjdaV2ZsQU94MnM',
            '0B4qLcYyJmiz0Tksyd21vRmVqamc', '0B4qLcYyJmiz0Tl9wNEU2WWRqcE0',
            '0B4qLcYyJmiz0TlBCNFU3QkctNkk', '0B4qLcYyJmiz0TlNyLUtOTzk3QjQ',
            '0B4qLcYyJmiz0Tlhvdl9zYlV4UUE', '0B4qLcYyJmiz0TlpJU1pleF9zbnM',
            '0B4qLcYyJmiz0Tm5MSUp3ZTZ0aTg', '0B4qLcYyJmiz0TmRZTmZyenViSjg',
            '0B4qLcYyJmiz0TmVkVGJmWEtVbFk', '0B4qLcYyJmiz0TmZqZXN3UWFkUm8',
            '0B4qLcYyJmiz0TmhIUGlVeE5pWjg', '0B4qLcYyJmiz0TnBtdW83OXRfdG8',
            '0B4qLcYyJmiz0TnJQSS1vZS1JYUE', '0B4qLcYyJmiz0TzBBNE8xbFhaSlU',
            '0B4qLcYyJmiz0TzZySG9IWlZaeGc', '0B4qLcYyJmiz0U05ZNG14X3ZjYW8',
            '0B4qLcYyJmiz0U0YwQmluMmJuX2M', '0B4qLcYyJmiz0U0lYX1J1Tk5vMjQ',
            '0B4qLcYyJmiz0U0tBanQ4cHNBUWc', '0B4qLcYyJmiz0U1BRYl9tSWFWVGM',
            '0B4qLcYyJmiz0U1BhWlFGRXc1aHc', '0B4qLcYyJmiz0U1pnMEI4WXN1S3M'
        ]

    for filename, drive_id in zip(filenames, drive_ids):
        print('Deal with file: ' + filename)
        output_path = os.path.join(global_data_dir, filename)
        tmp_confirm_file = '/tmp/gdrive_confirm.txt'
        confirm = subprocess.check_output(['wget', '--quiet', '--save-cookies', '/tmp/cookies.txt', '--keep-session-cookies', '--no-check-certificate', 'https://docs.google.com/uc?export=download&id={}'.format(drive_id), '-O-'])
        with open(tmp_confirm_file, 'w') as fout:
            fout.write(confirm.decode("utf-8"))
        parse_confirm = subprocess.check_output(['sed', '-rn', 's/.*confirm=([0-9A-Za-z_]+).*/\\1\\n/p', tmp_confirm_file])
        parse_confirm = parse_confirm.decode('utf-8')[0:-1]
        string = "https://docs.google.com/uc?export=download&confirm={0}&id={1}".format(parse_confirm, drive_id)
        output_info = subprocess.check_output(['wget', '--load-cookies', '/tmp/cookies.txt', string, '-O', output_path])
        subprocess.check_call(['rm', '-rf', '/tmp/cookies.txt'])
        subprocess.check_call(['rm', '-rf', tmp_confirm_file])
