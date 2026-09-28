from flask import Flask, request, jsonify
import asyncio
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad
import binascii
import aiohttp
import requests
import json
import like_pb2
import like_count_pb2
import uid_generator_pb2
import threading
import urllib3
import random


# ============================================================
# CONFIGURATION
# ============================================================

TOKEN_BATCH_SIZE = 100

urllib3.disable_warnings(
    urllib3.exceptions.InsecureRequestWarning
)


# ============================================================
# GLOBAL STATE
# ============================================================

current_batch_indices = {}
batch_indices_lock = threading.Lock()


# ============================================================
# TOKEN BATCH MANAGEMENT
# ============================================================

def get_next_batch_tokens(server_name, all_tokens):
    if not all_tokens:
        return []

    total_tokens = len(all_tokens)

    if total_tokens <= TOKEN_BATCH_SIZE:
        return all_tokens.copy()

    with batch_indices_lock:

        if server_name not in current_batch_indices:
            current_batch_indices[server_name] = 0

        current_index = current_batch_indices[server_name]

        start_index = current_index
        end_index = start_index + TOKEN_BATCH_SIZE

        if end_index > total_tokens:

            remaining = end_index - total_tokens

            batch_tokens = (
                all_tokens[start_index:total_tokens]
                + all_tokens[0:remaining]
            )

        else:

            batch_tokens = all_tokens[
                start_index:end_index
            ]

        next_index = (
            current_index + TOKEN_BATCH_SIZE
        ) % total_tokens

        current_batch_indices[server_name] = next_index

        return batch_tokens


def get_random_batch_tokens(server_name, all_tokens):
    """
    Randomly select tokens without replacement.
    """

    if not all_tokens:
        return []

    total_tokens = len(all_tokens)

    if total_tokens <= TOKEN_BATCH_SIZE:
        return all_tokens.copy()

    return random.sample(
        all_tokens,
        TOKEN_BATCH_SIZE
    )


# ============================================================
# TOKEN FILE LOADER
# ============================================================

def load_tokens(server_name, for_visit=False):

    server_name = server_name.upper()

    # --------------------------------------------------------
    # VISIT TOKENS
    # --------------------------------------------------------

    if for_visit:

        if server_name == "IND":
            path = "token_ind_visit.json"

        elif server_name == "ID":
            path = "token_id_visit.json"

        elif server_name in {
            "BR",
            "US",
            "SAC",
            "NA"
        }:
            path = "token_br_visit.json"

        else:
            path = "token_bd_visit.json"

    # --------------------------------------------------------
    # REGULAR TOKENS
    # --------------------------------------------------------

    else:

        if server_name == "IND":
            path = "token_ind.json"

        elif server_name == "ID":
            path = "token_id.json"

        elif server_name in {
            "BR",
            "US",
            "SAC",
            "NA"
        }:
            path = "token_br.json"

        else:
            path = "token_bd.json"

    # --------------------------------------------------------
    # LOAD JSON
    # --------------------------------------------------------

    try:

        with open(path, "r") as f:
            tokens = json.load(f)

        if (
            isinstance(tokens, list)
            and all(
                isinstance(t, dict)
                and "token" in t
                for t in tokens
            )
        ):

            print(
                f"[TOKEN] Loaded {len(tokens)} tokens "
                f"from {path} for server {server_name}"
            )

            return tokens

        print(
            f"[TOKEN] Invalid format: {path}"
        )

        return []

    except FileNotFoundError:

        print(
            f"[TOKEN] File not found: {path}"
        )

        return []

    except json.JSONDecodeError:

        print(
            f"[TOKEN] Invalid JSON: {path}"
        )

        return []

    except Exception as e:

        print(
            f"[TOKEN] Error loading {path}: {e}"
        )

        return []


# ============================================================
# AES ENCRYPTION
# ============================================================

def encrypt_message(plaintext):

    key = b'Yg&tc%DEuh6%Zc^8'
    iv = b'6oyZDr22E3ychjM%'

    cipher = AES.new(
        key,
        AES.MODE_CBC,
        iv
    )

    padded_message = pad(
        plaintext,
        AES.block_size
    )

    encrypted_message = cipher.encrypt(
        padded_message
    )

    return binascii.hexlify(
        encrypted_message
    ).decode("utf-8")


# ============================================================
# LIKE PROTOBUF
# ============================================================

def create_protobuf_message(
    user_id,
    region
):

    message = like_pb2.like()

    message.uid = int(user_id)
    message.region = region

    return message.SerializeToString()


# ============================================================
# PROFILE PROTOBUF
# ============================================================

def create_protobuf_for_profile_check(uid):

    message = uid_generator_pb2.uid_generator()

    message.krishna_ = int(uid)
    message.teamXdarks = 1

    return message.SerializeToString()


def enc_profile_check_payload(uid):

    protobuf_data = (
        create_protobuf_for_profile_check(uid)
    )

    encrypted_uid = encrypt_message(
        protobuf_data
    )

    return encrypted_uid


# ============================================================
# LIKE REQUEST
# ============================================================

async def send_single_like_request(
    encrypted_like_payload,
    token_dict,
    url
):

    try:

        edata = bytes.fromhex(
            encrypted_like_payload
        )

    except Exception as e:

        print(
            f"[LIKE] Invalid encrypted payload: {e}"
        )

        return 997

    token_value = token_dict.get(
        "token",
        ""
    )

    if not token_value:

        print(
            "[LIKE] Empty token"
        )

        return 999

    headers = {

        "User-Agent":
            "Dalvik/2.1.0 "
            "(Linux; U; Android 9; "
            "ASUS_Z01QD Build/PI)",

        "Connection":
            "Keep-Alive",

        "Accept-Encoding":
            "gzip",

        "Authorization":
            f"Bearer {token_value}",

        "Content-Type":
            "application/x-www-form-urlencoded",

        "Expect":
            "100-continue",

        "X-Unity-Version":
            "2018.4.12f1",

        "X-GA":
            "v1 1",

        "ReleaseVersion":
            "OB55"
    }

    try:

        timeout = aiohttp.ClientTimeout(
            total=10
        )

        async with aiohttp.ClientSession(
            timeout=timeout
        ) as session:

            async with session.post(
                url,
                data=edata,
                headers=headers
            ) as response:

                status = response.status

                if status != 200:

                    print(
                        "[LIKE] Request failed "
                        f"status={status}"
                    )

                return status

    except asyncio.TimeoutError:

        print(
            "[LIKE] Request timeout"
        )

        return 998

    except Exception as e:

        print(
            f"[LIKE] Exception: {e}"
        )

        return 997


# ============================================================
# SEND LIKE BATCH
# ============================================================

async def send_likes_with_token_batch(
    uid,
    server_region_for_like_proto,
    like_api_url,
    token_batch_to_use
):

    if not token_batch_to_use:

        print(
            "[LIKE] No tokens in batch"
        )

        return {
            "total": 0,
            "success": 0,
            "failed": 0,
            "status_codes": {}
        }

    # --------------------------------------------------------
    # CREATE PAYLOAD
    # --------------------------------------------------------

    try:

        like_protobuf_payload = (
            create_protobuf_message(
                uid,
                server_region_for_like_proto
            )
        )

        encrypted_like_payload = (
            encrypt_message(
                like_protobuf_payload
            )
        )

    except Exception as e:

        print(
            f"[LIKE] Payload error: {e}"
        )

        return {
            "total": len(token_batch_to_use),
            "success": 0,
            "failed": len(token_batch_to_use),
            "status_codes": {
                "payload_error": len(
                    token_batch_to_use
                )
            }
        }

    # --------------------------------------------------------
    # CREATE TASKS
    # --------------------------------------------------------

    tasks = []

    for token_dict in token_batch_to_use:

        tasks.append(
            send_single_like_request(
                encrypted_like_payload,
                token_dict,
                like_api_url
            )
        )

    # --------------------------------------------------------
    # EXECUTE
    # --------------------------------------------------------

    try:

        results = await asyncio.gather(
            *tasks,
            return_exceptions=True
        )

    except Exception as e:

        print(
            f"[LIKE] Gather exception: {e}"
        )

        return {
            "total": len(token_batch_to_use),
            "success": 0,
            "failed": len(token_batch_to_use),
            "status_codes": {
                "gather_exception": len(
                    token_batch_to_use
                )
            }
        }

    # --------------------------------------------------------
    # STATUS CODE SUMMARY
    # --------------------------------------------------------

    status_codes = {}

    for result in results:

        if isinstance(result, int):

            key = str(result)

        else:

            key = "exception"

        status_codes[key] = (
            status_codes.get(key, 0) + 1
        )

    # --------------------------------------------------------
    # SUCCESS / FAILED
    # --------------------------------------------------------

    successful_sends = sum(
        1
        for result in results
        if isinstance(result, int)
        and result == 200
    )

    failed_sends = (
        len(token_batch_to_use)
        - successful_sends
    )

    # --------------------------------------------------------
    # LOG
    # --------------------------------------------------------

    print(
        f"[LIKE] Total="
        f"{len(token_batch_to_use)} "
        f"Success="
        f"{successful_sends} "
        f"Failed="
        f"{failed_sends}"
    )

    print(
        f"[LIKE] HTTP status: "
        f"{status_codes}"
    )

    # --------------------------------------------------------
    # RESULT
    # --------------------------------------------------------

    return {
        "total": len(token_batch_to_use),
        "success": successful_sends,
        "failed": failed_sends,
        "status_codes": status_codes
    }


# ============================================================
# PROFILE ENDPOINT
# ============================================================

def get_profile_url(server_name):

    server_name = server_name.upper()

    if server_name == "IND":

        return (
            "https://client.ind.freefiremobile.com/"
            "GetPlayerPersonalShow"
        )

    elif server_name == "ID":

        return (
            "https://clientbp.ggpolarbear.com/"
            "GetPlayerPersonalShow"
        )

    elif server_name in {
        "BR",
        "US",
        "SAC",
        "NA"
    }:

        return (
            "https://client.us.freefiremobile.com/"
            "GetPlayerPersonalShow"
        )

    else:

        return (
            "https://clientbp.ggblueshark.com/"
            "GetPlayerPersonalShow"
        )


# ============================================================
# LIKE ENDPOINT
# ============================================================

def get_like_url(server_name):

    server_name = server_name.upper()

    if server_name == "IND":

        return (
            "https://client.ind.freefiremobile.com/"
            "LikeProfile"
        )

    elif server_name == "ID":

        return (
            "https://clientbp.ggpolarbear.com/"
            "LikeProfile"
        )

    elif server_name in {
        "BR",
        "US",
        "SAC",
        "NA"
    }:

        return (
            "https://client.us.freefiremobile.com/"
            "LikeProfile"
        )

    else:

        return (
            "https://clientbp.ggblueshark.com/"
            "LikeProfile"
        )


# ============================================================
# PROFILE CHECK REQUEST
# ============================================================

def make_profile_check_request(
    encrypted_profile_payload,
    server_name,
    token_dict
):

    token_value = token_dict.get(
        "token",
        ""
    )

    if not token_value:

        print(
            "[PROFILE] Empty token"
        )

        return None

    url = get_profile_url(
        server_name
    )

    try:

        edata = bytes.fromhex(
            encrypted_profile_payload
        )

    except Exception as e:

        print(
            f"[PROFILE] Invalid payload: {e}"
        )

        return None

    headers = {

        "User-Agent":
            "Dalvik/2.1.0 "
            "(Linux; U; Android 9; "
            "ASUS_Z01QD Build/PI)",

        "Connection":
            "Keep-Alive",

        "Accept-Encoding":
            "gzip",

        "Authorization":
            f"Bearer {token_value}",

        "Content-Type":
            "application/x-www-form-urlencoded",

        "Expect":
            "100-continue",

        "X-Unity-Version":
            "2018.4.12f1",

        "X-GA":
            "v1 1",

        "ReleaseVersion":
            "OB55"
    }

    try:

        response = requests.post(
            url,
            data=edata,
            headers=headers,
            verify=False,
            timeout=10
        )

        response.raise_for_status()

        binary_data = response.content

        return decode_protobuf_profile_info(
            binary_data
        )

    except requests.exceptions.HTTPError as e:

        status_code = (
            e.response.status_code
            if e.response
            else "?"
        )

        print(
            "[PROFILE] HTTP error: "
            f"{status_code}"
        )

    except requests.exceptions.RequestException as e:

        print(
            f"[PROFILE] Request error: {e}"
        )

    except Exception as e:

        print(
            f"[PROFILE] Unexpected error: {e}"
        )

    return None


# ============================================================
# DECODE PROFILE
# ============================================================

def decode_protobuf_profile_info(
    binary_data
):

    try:

        items = like_count_pb2.Info()

        items.ParseFromString(
            binary_data
        )

        return items

    except Exception as e:

        print(
            f"[PROTOBUF] Decode error: {e}"
        )

        return None


# ============================================================
# FLASK
# ============================================================

app = Flask(__name__)


# ============================================================
# /LIKE
# ============================================================

@app.route(
    "/like",
    methods=["GET"]
)
def handle_requests():

    try:

        # ----------------------------------------------------
        # PARAMETERS
        # ----------------------------------------------------

        uid_param = request.args.get(
            "uid"
        )

        server_name_param = (
            request.args
            .get(
                "server_name",
                ""
            )
            .upper()
        )

        use_random = (
            request.args
            .get(
                "random",
                "false"
            )
            .lower()
            == "true"
        )

        # ----------------------------------------------------
        # VALIDATION
        # ----------------------------------------------------

        if not uid_param:

            return jsonify({
                "error":
                    "UID is required"
            }), 400

        if not server_name_param:

            return jsonify({
                "error":
                    "server_name is required"
            }), 400

        try:

            int(uid_param)

        except ValueError:

            return jsonify({
                "error":
                    "UID must be numeric"
            }), 400

        # ----------------------------------------------------
        # ALLOWED SERVERS
        # ----------------------------------------------------

        allowed_servers = {
            "ID",
            "IND",
            "BD",
            "BR",
            "US",
            "SAC",
            "NA"
        }

        if server_name_param not in allowed_servers:

            return jsonify({
                "error":
                    "Unsupported server",
                "allowed_servers":
                    sorted(allowed_servers)
            }), 400

        # ----------------------------------------------------
        # LOAD VISIT TOKENS
        # ----------------------------------------------------

        visit_tokens = load_tokens(
            server_name_param,
            for_visit=True
        )

        if not visit_tokens:

            return jsonify({
                "error":
                    f"No visit tokens loaded "
                    f"for server "
                    f"{server_name_param}."
            }), 500

        visit_token = visit_tokens[0]

        # ----------------------------------------------------
        # LOAD REGULAR TOKENS
        # ----------------------------------------------------

        all_available_tokens = load_tokens(
            server_name_param,
            for_visit=False
        )

        if not all_available_tokens:

            return jsonify({
                "error":
                    f"No regular tokens loaded "
                    f"for server "
                    f"{server_name_param}."
            }), 500

        print(
            f"[API] Server={server_name_param} "
            f"UID={uid_param} "
            f"Tokens={len(all_available_tokens)}"
        )

        # ----------------------------------------------------
        # SELECT TOKEN BATCH
        # ----------------------------------------------------

        if use_random:

            tokens_for_like_sending = (
                get_random_batch_tokens(
                    server_name_param,
                    all_available_tokens
                )
            )

            batch_mode = "random"

        else:

            tokens_for_like_sending = (
                get_next_batch_tokens(
                    server_name_param,
                    all_available_tokens
                )
            )

            batch_mode = "rotating"

        # ----------------------------------------------------
        # PROFILE PAYLOAD
        # ----------------------------------------------------

        encrypted_player_uid_for_profile = (
            enc_profile_check_payload(
                uid_param
            )
        )

        # ----------------------------------------------------
        # BEFORE
        # ----------------------------------------------------

        before_info = (
            make_profile_check_request(
                encrypted_player_uid_for_profile,
                server_name_param,
                visit_token
            )
        )

        before_like_count = 0

        if (
            before_info
            and hasattr(
                before_info,
                "AccountInfo"
            )
        ):

            before_like_count = int(
                before_info.AccountInfo.Likes
            )

        print(
            f"[API] UID={uid_param} "
            f"Likes before={before_like_count}"
        )

        # ----------------------------------------------------
        # SEND LIKES
        # ----------------------------------------------------

        like_api_url = get_like_url(
            server_name_param
        )

        like_result = {
            "total": 0,
            "success": 0,
            "failed": 0,
            "status_codes": {}
        }

        if tokens_for_like_sending:

            loop = asyncio.new_event_loop()

            try:

                asyncio.set_event_loop(
                    loop
                )

                like_result = (
                    loop.run_until_complete(
                        send_likes_with_token_batch(
                            uid_param,
                            server_name_param,
                            like_api_url,
                            tokens_for_like_sending
                        )
                    )
                )

            except Exception as e:

                print(
                    f"[LIKE] Batch error: {e}"
                )

                like_result = {
                    "total":
                        len(
                            tokens_for_like_sending
                        ),

                    "success": 0,

                    "failed":
                        len(
                            tokens_for_like_sending
                        ),

                    "status_codes": {
                        "batch_exception": 1
                    }
                }

            finally:

                try:
                    loop.close()
                except Exception:
                    pass

        # ----------------------------------------------------
        # AFTER
        # ----------------------------------------------------

        after_info = (
            make_profile_check_request(
                encrypted_player_uid_for_profile,
                server_name_param,
                visit_token
            )
        )

        after_like_count = (
            before_like_count
        )

        actual_player_uid = int(
            uid_param
        )

        player_nickname = "N/A"

        if (
            after_info
            and hasattr(
                after_info,
                "AccountInfo"
            )
        ):

            after_like_count = int(
                after_info.AccountInfo.Likes
            )

            actual_player_uid = int(
                after_info.AccountInfo.UID
            )

            if (
                after_info.AccountInfo.PlayerNickname
            ):

                player_nickname = str(
                    after_info.AccountInfo.PlayerNickname
                )

        print(
            f"[API] UID={uid_param} "
            f"Likes after={after_like_count}"
        )

        # ----------------------------------------------------
        # CALCULATE RESULT
        # ----------------------------------------------------

        likes_increment = (
            after_like_count
            - before_like_count
        )

        if likes_increment > 0:

            request_status = 1

        elif likes_increment == 0:

            request_status = 2

        else:

            request_status = 3

        # ----------------------------------------------------
        # RESPONSE
        # ----------------------------------------------------

        response_data = {

            "LikesGivenByAPI":
                likes_increment,

            "LikesafterCommand":
                after_like_count,

            "LikesbeforeCommand":
                before_like_count,

            "PlayerNickname":
                player_nickname,

            "UID":
                actual_player_uid,

            "status":
                request_status,

            "server":
                server_name_param,

            "batch_mode":
                batch_mode,

            "tokens_used":
                len(
                    tokens_for_like_sending
                ),

            "like_requests":
                like_result,

            "Note":
                "Profile checked before and after the like request."
        }

        return jsonify(
            response_data
        )

    except Exception as e:

        print(
            f"[API] Unhandled error: {e}"
        )

        return jsonify({
            "error":
                "Internal server error",
            "message":
                str(e)
        }), 500


# ============================================================
# /TOKEN_INFO
# ============================================================

@app.route(
    "/token_info",
    methods=["GET"]
)
def token_info():

    try:

        servers = [
            "ID",
            "IND",
            "BD",
            "BR",
            "US",
            "SAC",
            "NA"
        ]

        info = {}

        for server in servers:

            regular_tokens = load_tokens(
                server,
                for_visit=False
            )

            visit_tokens = load_tokens(
                server,
                for_visit=True
            )

            info[server] = {

                "regular_tokens":
                    len(regular_tokens),

                "visit_tokens":
                    len(visit_tokens)

            }

        return jsonify(info)

    except Exception as e:

        print(
            f"[TOKEN_INFO] Error: {e}"
        )

        return jsonify({
            "error":
                "Internal server error",
            "message":
                str(e)
        }), 500


# ============================================================
# HEALTH CHECK
# ============================================================

@app.route(
    "/",
    methods=["GET"]
)
def home():

    return jsonify({

        "status":
            "online",

        "service":
            "Like API",

        "servers": [
            "ID",
            "IND",
            "BD",
            "BR",
            "US",
            "SAC",
            "NA"
        ],

        "endpoints": [
            "/like",
            "/token_info"
        ]

    })


# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":

    app.run(
        host="0.0.0.0",
        port=5001,
        debug=True,
        use_reloader=False
    )
