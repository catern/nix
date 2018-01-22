import nar
import construct
from construct import Struct, Const, Int64ul, Pass
from types import SimpleNamespace

#### version-independent helper types
nixstr = construct.Aligned(8, construct.PascalString(construct.Int64ul, encoding="utf8"))
nixstr_array = construct.PrefixedArray(Int64ul, nixstr)

#### version-independent connection initialization messages
client_hello = Const(b"cxin\0\0\0\0")
server_hello_version = construct.FocusedSeq(
    1,
    Const(b"oixd\0\0\0\0"),
    Int64ul
)
client_version = Int64ul

#### all version-specific messages
def get_constructors_for_version(server_version, client_version):
    self = SimpleNamespace()
    #### additional initial options sent by client
    self.client_initial_options = Struct(
        # determines whether the next field is present or not
        # TODO figure out how to parse/build when this is 0
        Const(Int64ul, 1),
        "cpu_affinity"/ Int64ul,
        # obsolete, only on server >= 11
        Const(Int64ul, 0),
    )

    self.op_type, self.op_request, self.op_response = operations(server_version, client_version)
    self.stderr_type, self.stderr_message = stderr(server_version, client_version)
    return self

def operations(server_version, client_version):
    #### operation type enum
    op_to_num = {
        "wopIsValidPath": 1,
        "wopHasSubstitutes": 3,
        "wopQueryPathHash": 4,
        "wopQueryReferences": 5,
        "wopQueryReferrers": 6,
        "wopAddToStore": 7,
        "wopAddTextToStore": 8,
        "wopBuildPaths": 9,
        "wopEnsurePath": 10,
        "wopAddTempRoot": 11,
        "wopAddIndirectRoot": 12,
        "wopSyncWithGC": 13,
        "wopFindRoots": 14,
        "wopExportPath": 16,
        "wopQueryDeriver": 18,
        "wopSetOptions": 19,
        "wopCollectGarbage": 20,
        "wopQuerySubstitutablePathInfo": 21,
        "wopQueryDerivationOutputs": 22,
        "wopQueryAllValidPaths": 23,
        "wopQueryFailedPaths": 24,
        "wopClearFailedPaths": 25,
        "wopQueryPathInfo": 26,
        "wopImportPaths": 27,
        "wopQueryDerivationOutputNames": 28,
        "wopQueryPathFromHashPart": 29,
        "wopQuerySubstitutablePathInfos": 30,
        "wopQueryValidPaths": 31,
        "wopQuerySubstitutablePaths": 32,
        "wopQueryValidDerivers": 33,
        "wopOptimiseStore": 34,
        "wopVerifyStore": 35,
        "wopBuildDerivation": 36,
        "wopAddSignatures": 37,
        "wopNarFromPath": 38,
        "wopAddToStoreNar": 39,
        "wopQueryMissing": 40,
    }
    op_type = construct.Enum(Int64ul, **op_to_num)
    
    #### operation requests
    wopSetOptions = Struct(
        "keepFailed" / Int64ul,
        "keepGoing" / Int64ul,
        "tryFallback" / Int64ul,
        "verbosity" / Int64ul,
        "maxBuildJobs" / Int64ul,
        "maxSilentTime" / Int64ul,
        "useBuildHook" / Int64ul,
        "verboseBuild" / Int64ul,
        "logType" / Int64ul,
        "printBuildTrace" / Int64ul,
        "buildCores" / Int64ul,
        "useSubstitutes" / Int64ul,
        "overrides" / construct.PrefixedArray(Int64ul, Struct(
            "option" / nixstr,
            "value" / nixstr
        ))
    )
    wopAddToStore = Struct(
        "baseName" / nixstr,
        "fixed" / Int64ul,
        "recursive" / Int64ul,
        "hashType" / nixstr,
        "nar" / nar.dump
    )
    wopAddTextToStore = Struct(
        "baseName" / nixstr,
        "string" / nixstr,
        "references" / nixstr_array
    )
    wopBuildPaths = Struct(
        "paths" / nixstr_array,
        "mode" / Int64ul
    )
    wopQuerySubstitutablePathInfos = Struct(
        "paths" / nixstr_array,
    )
    gc_action_to_num = {
        "gcReturnLive": 0,
        "gcReturnDead": 1,
        "gcDeleteDead": 2,
        "gcDeleteSpecific": 3,
    }
    gc_action_enum = construct.Enum(Int64ul, **gc_action_to_num)
    wopCollectGarbage = Struct(
        "action" / gc_action_enum,
        "pathsToDelete" / nixstr_array,
        "ignoreLiveness" / Int64ul,
        "maxFreed" / Int64ul,
        # obsolete fields
        construct.Const(Int64ul, 0),
        construct.Const(Int64ul, 0),
        construct.Const(Int64ul, 0)
    )
    type_to_op_request = {
        "wopFindRoots"  : Struct(),
        "wopSyncWithGC" : Struct(),
        "wopIsValidPath"            : Struct("path"/nixstr),
        "wopEnsurePath"             : Struct("path"/nixstr),
        "wopQueryPathInfo"          : Struct("path"/nixstr),
        "wopQueryReferrers"         : Struct("path"/nixstr),
        "wopQueryDerivationOutputs" : Struct("path"/nixstr),
        "wopAddTempRoot"            : Struct("path"/nixstr),
        "wopAddIndirectRoot"        : Struct("path"/nixstr),
        "wopSetOptions":wopSetOptions,
        "wopAddToStore":wopAddToStore,
        "wopAddTextToStore":wopAddTextToStore,
        "wopBuildPaths":wopBuildPaths,
        "wopQuerySubstitutablePathInfos":wopQuerySubstitutablePathInfos,
        "wopCollectGarbage":wopCollectGarbage,
    }
    
    #### operation responses
    map_entry = Struct(
        "key" / nixstr,
        "value" / nixstr
    )
    map_response = Struct(
        "entries" / construct.PrefixedArray(Int64ul, map_entry)
    )
    pathinfo_response = Struct(
        # daemon version 17 and above
        # "valid" / Int64ul,
        "deriver"/nixstr,
        "narHash"/nixstr,
        "references" / nixstr_array,
        "registrationTime"/Int64ul,
        "narSize"/Int64ul,
        # daemon version 16 and above
        # "ultimate"/Int64ul,
        # "sigs" / nixstr_array,
        # "ca"/nixstr,
    )
    wopCollectGarbage_response = Struct(
        "collectedPaths" / nixstr_array,
        "bytesFreed"/Int64ul,
        # obsolete
        construct.Const(Int64ul, 0),
    )
    substitutable_pathinfo = Struct(
        "path"/nixstr,
        "deriver"/nixstr,
        "references"/nixstr_array,
        "downloadSize"/Int64ul,
        "narSize"/Int64ul
    )
    wopQuerySubstitutablePathInfos_response = Struct(
        "infos" / construct.PrefixedArray(Int64ul, substitutable_pathinfo)
    )
    type_to_op_response = {
        "wopSetOptions": Struct(),
        "wopIsValidPath"     : Struct("ret"/Int64ul),
        "wopEnsurePath"      : Struct("ret"/Int64ul),
        "wopBuildPaths"      : Struct("ret"/Int64ul),
        "wopAddTempRoot"     : Struct("ret"/Int64ul),
        "wopAddIndirectRoot" : Struct("ret"/Int64ul),
        "wopSyncWithGC"      : Struct("ret"/Int64ul),
        "wopAddToStore"     : Struct("path"/nixstr),
        "wopAddTextToStore" : Struct("path"/nixstr),
        "wopQueryReferrers"         : Struct("paths"/nixstr_array),
        "wopQueryDerivationOutputs" : Struct("paths"/nixstr_array),
        "wopFindRoots": map_response,
        "wopQueryPathInfo": pathinfo_response,
        "wopQuerySubstitutablePathInfos": wopQuerySubstitutablePathInfos_response,
        "wopCollectGarbage": wopCollectGarbage_response,
    }
    return op_type, type_to_op_request, type_to_op_response

def stderr(server_version, client_version):
    #### stderr message type enum
    stderr_message_to_num = {
        "STDERR_NEXT": 0x6f6c6d67,
        "STDERR_READ": 0x64617461,
        "STDERR_WRITE": 0x64617416,
        "STDERR_LAST": 0x616c7473,
        "STDERR_ERROR": 0x63787470,
        "STDERR_START_ACTIVITY": 0x53545254,
        "STDERR_STOP_ACTIVITY": 0x53544f50,
        "STDERR_RESULT": 0x52534c54,
    }
    stderr_message_type = construct.Enum(Int64ul, **stderr_message_to_num)
    
    #### stderr messages
    stderr_error = Struct(
        "error"/nixstr,
        "status"/Int64ul
    )
    logger_field_type_enum = construct.Enum(Int64ul,
        int=0,
        string=1
    )
    logger_field = construct.Select(
        Struct(
            "type"/Const(logger_field_type_enum, "int"),
            "number"/Int64ul
        ),
        Struct(
            "type"/Const(logger_field_type_enum, "string"),
            "number"/nixstr
    ))
    activity_id = Int64ul
    verbosity_level_to_dict = {
        "lvlError": 0,
        "lvlInfo": 1,
        "lvlTalkative": 2,
        "lvlChatty": 3,
        "lvlDebug": 4,
        "lvlVomit": 5,
    }
    verbosity_level_enum = construct.Enum(Int64ul, **verbosity_level_to_dict)
    activity_type_to_dict = {
        "actUnknown": 0,
        "actCopyPath": 100,
        "actDownload": 101,
        "actRealise": 102,
        "actCopyPaths": 103,
        "actBuilds": 104,
        "actBuild": 105,
        "actOptimiseStore": 106,
        "actVerifyPaths": 107,
        "actSubstitute": 108,
        "actQueryPathInfo": 109,
    }
    activity_type_enum = construct.Enum(Int64ul, **activity_type_to_dict)
    stderr_start_activity = Struct(
        "activity"/activity_id,
        "verbosity_level"/verbosity_level_enum,
        "activity_type"/activity_type_enum,
        "string"/nixstr,
        "fields"/construct.PrefixedArray(Int64ul, logger_field),
        "parent"/activity_id
    )
    stderr_stop_activity = Struct(
        "activity"/activity_id
    )
    result_type_to_dict = {
        "resFileLinked": 100,
        "resBuildLogLine": 101,
        "resUntrustedPath": 102,
        "resCorruptedPath": 103,
        "resSetPhase": 104,
        "resProgress": 105,
        "resSetExpected": 106,
    }
    result_type_enum = construct.Enum(Int64ul, **result_type_to_dict)
    stderr_result = Struct(
        "activity"/activity_id,
        "result_type"/result_type_enum,
        "fields"/construct.PrefixedArray(Int64ul, logger_field),
    )
    type_to_stderr_message = {
        "STDERR_WRITE": Struct("data"/nixstr),
        "STDERR_READ": Struct(),
        "STDERR_ERROR": stderr_error,
        "STDERR_NEXT": Struct("data"/nixstr),
        "STDERR_START_ACTIVITY": stderr_start_activity,
        "STDERR_STOP_ACTIVITY": stderr_stop_activity,
        "STDERR_RESULT": stderr_result,
        "STDERR_LAST": Struct(),
    }
    return stderr_message_type, type_to_stderr_message

