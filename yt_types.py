from typing import TypedDict, Literal, List, Dict, Union


class Thumbnail(TypedDict, total=False):
    url: str
    width: int
    height: int


class ThumbnailKeys(TypedDict, total=False):
    default: Thumbnail
    medium: Thumbnail
    high: Thumbnail
    standard: Thumbnail
    maxres: Thumbnail


class Snippet(TypedDict, total=False):
    publishedAt: str
    channelId: str
    title: str
    description: str
    thumbnails: ThumbnailKeys


class BroadcastSnippet(Snippet):
    scheduledStartTime: str
    scheduledEndTime: str
    actualStartTime: str
    actualEndTime: str
    isDefaultBroadcast: bool
    liveChatId: str


class BroadcastStatus(TypedDict, total=False):
    lifeCycleStatus: str
    privacyStatus: str
    recordingStatus: str
    madeForKids: str
    selfDeclaredMadeForKids: str


class BroadcastMonitorStream(TypedDict, total=False):
    enableMonitorStream: bool
    broadcastStreamDelayMs: int
    embedHtml: str


class BroadcastContentDetails(TypedDict, total=False):
    boundStreamId: str
    boundStreamLastUpdateTimeMs: str
    monitorStream: BroadcastMonitorStream
    enableEmbed: bool
    enableDvr: bool
    enableContentEncryption: bool
    startWithSlate: bool
    recordFromStart: bool
    enableClosedCaptions: bool
    closedCaptionsType: str
    projection: str
    enableLowLatency: bool
    latencyPreference: bool
    enableAutoStart: bool
    enableAutoStop: bool


class BroadcastStatistics(TypedDict, total=False):
    totalChatCount: int


class YouTubeLiveBroadcast(TypedDict, total=False):
    kind: Literal['youtube#liveBroadcast']
    etag: str
    id: str
    snippet: BroadcastSnippet
    status: BroadcastStatus
    contentDetails: BroadcastContentDetails
    statistics: BroadcastStatistics


class PageInfo(TypedDict, total=False):
    totalResults: int
    resultsPerPage: int


class YouTubeLiveBroadcastList(TypedDict, total=False):
    kind: Literal['youtube#liveBroadcastListResponse']
    etag: str
    nextPageToken: str
    prevPageToken: str
    pageInfo: PageInfo
    items: List[YouTubeLiveBroadcast]


class StreamSnippet(TypedDict, total=False):
    publishedAt: str
    channelId: str
    title: str
    description: str
    isDefaultStream: bool


class StreamIngestionInfo(TypedDict, total=False):
    streamName: str
    ingestionAddress: str
    backupIngestionAddress: str


class StreamCdn(TypedDict, total=False):
    ingestionType: str
    ingestionInfo: StreamIngestionInfo
    resolution: str
    frameRate: str


class StreamConfigurationIssue(TypedDict, total=False):
    type: str
    severity: str
    reason: str
    description: str


class StreamHealthStatus(TypedDict, total=False):
    status: str
    lastUpdateTimeSeconds: int
    configurationIssues: List[StreamConfigurationIssue]


class StreamStatus(TypedDict, total=False):
    streamStatus: str
    healthStatus: StreamHealthStatus


class StreamContentDetails(TypedDict, total=False):
    closedCaptionsIngestionUrl: str
    isReusable: bool


class YouTubeLiveStream(TypedDict, total=False):
    kind: Literal['youtube#liveStream']
    etag: str
    id: str
    snippet: StreamSnippet
    cdn: StreamCdn
    status: StreamStatus
    contentDetails: StreamContentDetails


class YouTubeLiveStreamList(TypedDict, total=False):
    kind: Literal['youtube#liveStreamListResponse']
    etag: str
    nextPageToken: str
    prevPageToken: str
    pageInfo: PageInfo
    items: List[YouTubeLiveStream]


class PlaylistItemResourceId(TypedDict, total=False):
    kind: str
    videoId: str


class PlaylistItemSnippet(TypedDict, total=False):
    publishedAt: str
    channelId: str
    title: str
    description: str
    thumbnails: ThumbnailKeys
    channelTitle: str
    videoOwnerChannelTitle: str
    videoOwnerChannelId: str
    playlistId: str
    position: int
    resourceId: PlaylistItemResourceId


class PlaylistItemContentDetails(TypedDict, total=False):
    videoId: str
    startAt: str
    endAt: str
    note: str
    videoPublishedAt: str


class Status(TypedDict, total=False):
    privacyStatus: str


class YouTubePlaylistItem(TypedDict, total=False):
    kind: Literal['youtube#playlistItem']
    etag: str
    id: str
    snippet: PlaylistItemSnippet
    contentDetails: PlaylistItemContentDetails
    status: Status


class Localization(TypedDict, total=False):
    title: str
    description: str


class VideoSnippet(Snippet):
    channelTitle: str
    tags: List[str]
    categoryId: str
    liveBroadcastContent: str
    defaultLanguage: str
    localized: Localization
    defaultAudioLanguage: str


class YouTubeVideo(TypedDict, total=False):
    kind: Literal['youtube#video']
    etag: str
    id: str
    snippet: VideoSnippet
    contentDetails: Dict[str, Union[str, bool, Dict[str, Union[str, List[str]]],]]
    status: Dict[str, Union[str, bool]]
    statistics: Dict[str, int]
    player: Dict[str, Union[str, int]]
    topicDetails: Dict[str, List[str]]
    recordingDetails: Dict[str, str]
    fileDetails: Dict[str, Union[str, int, List[Dict[str, Union[int, float, str]]]]]
    processingDetails: Dict[str, Union[str, Dict[str, int]]]
    suggestions: Dict[str, Union[List[str], Dict[str, Union[str, List[str]]]]]
    liveStreamingDetails: Dict[str, Union[str, int]]
    localizations: Dict[str, Dict[str, str]]


class YouTubeVideoList(TypedDict, total=False):
    kind: Literal['youtube#videoListResponse']
    etag: str
    nextPageToken: str
    prevPageToken: str
    pageInfo: PageInfo
    items: List[YouTubeVideo]


class PlaylistSnippet(Snippet):
    channelTitle: str
    defaultLanguage: str
    localized: Localization


class PlaylistContentDetails(TypedDict, total=False):
    itemCount: int


class PlaylistPlayer(TypedDict, total=False):
    embedHtml: str


class YouTubePlaylist(TypedDict, total=False):
    kind: Literal['youtube#playlist']
    etag: str
    id: str
    snippet: PlaylistSnippet
    status: Status
    contentDetails: PlaylistContentDetails
    player: PlaylistPlayer
    localizations: Dict[str, Dict[str, str]]


class YouTubePlaylistList(TypedDict, total=False):
    kind: Literal['youtube#playlistListResponse']
    etag: str
    nextPageToken: str
    prevPageToken: str
    pageInfo: PageInfo
    items: List[YouTubePlaylist]
