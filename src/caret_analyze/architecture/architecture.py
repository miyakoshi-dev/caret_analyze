# Copyright 2021 TIER IV, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from __future__ import annotations

from collections.abc import Callable, Collection, Sequence
import logging

from .architecture_exporter import ArchitectureExporter
from .architecture_loaded import ArchitectureLoaded, NodeValuesLoaded
from .architecture_reader_factory import ArchitectureReaderFactory
from .combine_path import CombinePath
from .graph_search import NodePathSearcher

from .reader_interface import IGNORE_TOPICS
from .struct import (CallbackStruct, CommunicationStruct, ExecutorStruct,
                     NodePathStruct, NodeStruct, PathStruct,
                     ServiceCallbackStruct, SubscriptionCallbackStruct, TimerCallbackStruct)
from ..common import Summarizable, Summary, type_check_decorator, Util
from ..exceptions import InvalidArgumentError, ItemNotFoundError, UnsupportedTypeError
from ..value_objects import (CallbackGroupStructValue, CallbackStructValue,
                             CommunicationStructValue, DiffNode, ExecutorStructValue,
                             NodePathStructValue, NodeStructValue, PathStructValue,
                             PublisherStructValue, ServiceStructValue, SubscriptionStructValue)

logger = logging.getLogger(__name__)

DEFAULT_MAX_CALLBACK_CONSTRUCTION_ORDER_ON_PATH_SEARCHING = 10


class Architecture(Summarizable):
    def __init__(
        self,
        file_type: str,
        file_path: str | list[str],
        max_callback_construction_order_on_path_searching: int =
            DEFAULT_MAX_CALLBACK_CONSTRUCTION_ORDER_ON_PATH_SEARCHING
    ) -> None:
        self._max_callback_construction_order_on_path_searching = \
            max_callback_construction_order_on_path_searching

        # /parameter events and /rosout measurements are not yet supported.
        ignore_topics: list[str] = IGNORE_TOPICS

        reader = ArchitectureReaderFactory.create_instance(
            file_type, file_path)
        loaded = ArchitectureLoaded(reader,
                                    ignore_topics,
                                    max_callback_construction_order_on_path_searching)

        self._nodes: list[NodeStruct] = loaded.nodes
        self._communications: list[CommunicationStruct] = loaded.communications
        self._executors: list[ExecutorStruct] = loaded.executors
        self._paths = loaded.paths
        self._verify(self._nodes)

    def get_node(self, node_name: str) -> NodeStructValue:
        """
        Get node.

        Returns
        -------
        NodeStructValue
            Node struct value.

        Raises
        ------
        ItemNotFoundError
            Occurs when no items were found.
        MultipleItemFoundError
            Occurs when several items were found.

        """
        try:
            return Util.find_one(lambda x: x.node_name == node_name, self.nodes)
        except ItemNotFoundError:
            msg = 'Failed to find node. '
            msg += f'node_name: {node_name}'
            raise ItemNotFoundError(msg)

    def get_executor(self, executor_name: str) -> ExecutorStructValue:
        """
        Get executor.

        Returns
        -------
        ExecutorStructValue
            Executor struct value.

        Raises
        ------
        ItemNotFoundError
            Occurs when no items were found.
        MultipleItemFoundError
            Occurs when several items were found.

        """
        return Util.find_one(lambda x: x.executor_name == executor_name, self.executors)

    def get_callback_group(self, callback_group_name: str) -> CallbackGroupStructValue:
        """
        Get callback group.

        Returns
        -------
        CallbackGroupStructValue
            CallbackGroup struct value.

        Raises
        ------
        ItemNotFoundError
            Occurs when no items were found.
        MultipleItemFoundError
            Occurs when several items were found.

        """
        return Util.find_one(lambda x: x.callback_group_name == callback_group_name,
                             self.callback_groups)

    @property
    def callback_groups(self) -> tuple[CallbackGroupStructValue, ...]:
        """
        Get callback groups.

        Returns
        -------
        tuple[CallbackGroupStructValue, ...]
            CallbackGroup struct value.

        """
        cbg: list[CallbackGroupStructValue] = []
        for node in self.nodes:
            if node.callback_groups is not None:
                cbg += node.callback_groups
        return tuple(cbg)

    @property
    def callback_group_names(self) -> tuple[str, ...]:
        """
        Get callback group names.

        Returns
        -------
        tuple[str, ...]
            CallbackGroup names.

        """
        return tuple(sorted(_.callback_group_name for _ in self.callback_groups))

    @property
    def topic_names(self) -> tuple[str, ...]:
        """
        Get topic names.

        Returns
        -------
        tuple[str, ...]
            Topic names.

        """
        topic_names = {_.topic_name for _ in self.publishers}
        topic_names |= {_.topic_name for _ in self.subscriptions}
        return tuple(sorted(topic_names))

    def get_callback(self, callback_name: str) -> CallbackStructValue:
        """
        Get callback.

        Returns
        -------
        CallbackStructValue
            Callback struct value.

        Raises
        ------
        ItemNotFoundError
            Occurs when no items were found.
        MultipleItemFoundError
            Occurs when several items were found.

        """
        return Util.find_one(lambda x: x.callback_name == callback_name, self.callbacks)

    @property
    def callbacks(self) -> tuple[CallbackStructValue, ...]:
        """
        Get callbacks.

        Returns
        -------
        tuple[CallbackStructValue, ...]
            Callbacks.

        """
        return tuple(Util.flatten(_.callbacks for _ in self.callback_groups))

    def get_communication(
        self,
        publisher_node_name: str,
        subscription_node_name: str,
        topic_name: str,
        *,
        publisher_construction_order: int = 0,
        subscription_construction_order: int = 0
    ) -> CommunicationStructValue:
        """
        Get communication.

        Parameters
        ----------
        publisher_node_name : str
            Publisher node name.
        subscription_node_name : str
            Subscription node name.
        topic_name : str
            Topic name.
        publisher_construction_order : int
            Publisher construction order.
        subscription_construction_order : int
            Subscription construction order.

        Returns
        -------
        CommunicationStructValue
            Communication struct value.

        Raises
        ------
        ItemNotFoundError
            Occurs when no items were found.
        MultipleItemFoundError
            Occurs when several items were found.

        """
        def is_target_comm(comm: CommunicationStructValue):
            return comm.publish_node_name == publisher_node_name and \
                comm.subscribe_node_name == subscription_node_name and \
                comm.topic_name == topic_name and \
                comm.publisher_construction_order == publisher_construction_order and \
                comm.subscription_construction_order == subscription_construction_order

        return Util.find_one(is_target_comm, self.communications)

    def get_path(self, path_name: str) -> PathStructValue:
        """
        Get path name.

        Parameters
        ----------
        path_name : str
            Path name.

        Returns
        -------
        PathStructValue
            Path struct value.

        Raises
        ------
        InvalidArgumentError
            Occurs when path name were not exist.
        ItemNotFoundError
            Occurs when no items were found.
        MultipleItemFoundError
            Occurs when several items were found.

        """
        if path_name not in self.path_names:
            raise InvalidArgumentError(f'Failed to get named path. {path_name} not exist.')

        named_path: PathStruct = Util.find_one(lambda x: x._path_name == path_name, self._paths)
        return named_path.to_value()

    def add_path(self, path_name: str, path_info: PathStructValue) -> None:
        """
        Add path.

        Parameters
        ----------
        path_name : str
            Path name.
        path_info : PathStructValue
            path information.

        Raises
        ------
        InvalidArgumentError
            Occurs when path name were duplicate.
        ItemNotFoundError
            Occurs when no items were found.
        MultipleItemFoundError
            Occurs when several items were found.

        """
        if path_name in self.path_names:
            raise InvalidArgumentError('Failed to add named path. Duplicate path name.')

        child: list[NodePathStruct | CommunicationStruct] = []

        for c in path_info.child:
            if isinstance(c, NodePathStructValue):
                node_name = c.node_name
                publish_topic_name = c.publish_topic_name
                subscribe_topic_name = c.subscribe_topic_name
                publisher_construction_order = c.publisher_construction_order
                subscription_construction_order = c.subscription_construction_order

                def is_target_node(node: NodeStruct):
                    return node_name == node.node_name

                def is_target_node_path(node_path: NodePathStruct):
                    return (
                        publish_topic_name == node_path.publish_topic_name and
                        subscribe_topic_name == node_path.subscribe_topic_name and
                        publisher_construction_order ==
                        node_path.publisher_construction_order and
                        subscription_construction_order ==
                        node_path.subscription_construction_order
                    )

                node: NodeStruct = Util.find_one(is_target_node, self._nodes)
                node_path: NodePathStruct = Util.find_one(is_target_node_path, node.paths)
                child.append(node_path)

            elif isinstance(c, CommunicationStructValue):
                publish_node_name = c.publish_node_name
                subscribe_node_name = c.subscribe_node_name
                topic_name = c.topic_name
                publisher_construction_order = c.publisher_construction_order
                subscription_construction_order = c.subscription_construction_order

                def is_target_comm(comm: CommunicationStruct):
                    return publish_node_name == comm.publish_node_name and \
                        subscribe_node_name == comm.subscribe_node_name and \
                        topic_name == comm.topic_name and \
                        publisher_construction_order == comm.publisher_construction_order and \
                        subscription_construction_order == comm.subscription_construction_order

                comm: CommunicationStruct = \
                    Util.find_one(is_target_comm, self._communications)
                child.append(comm)

            else:
                raise UnsupportedTypeError('')

        named_path_info = PathStruct(path_name, child)
        self._paths.append(named_path_info)

    def remove_path(self, path_name: str) -> None:
        """
        Remove path.

        Parameters
        ----------
        path_name : str
            Path name.

        Raises
        ------
        InvalidArgumentError
            Occurs when path name were not exist.

        """
        if path_name not in self.path_names:
            raise InvalidArgumentError(f'Failed to remove named path. {path_name} not exist.')

        idx = None
        for i, p in enumerate(self._paths):
            if p.path_name == path_name:
                idx = i

        if idx is not None:
            self._paths.pop(idx)

    def update_path(self, path_name: str, path: PathStructValue) -> None:
        """
        Update path.

        Parameters
        ----------
        path_name : str
            Path name.
        path : PathStructValue
            Path struct value.

        Raises
        ------
        InvalidArgumentError
            Occurs when path name were not exist.

        """
        if path.path_name is None:
            raise InvalidArgumentError('path_info.path_name is None')

        self.remove_path(path.path_name)
        self.add_path(path_name, path)

    @property
    def nodes(self) -> tuple[NodeStructValue, ...]:
        """
        Get nodes.

        Returns
        -------
        tuple[NodeStructValue, ...]
            Node struct value.

        """
        return tuple(v.to_value() for v in self._nodes)

    @property
    def node_names(self) -> tuple[str, ...]:
        """
        Get node names.

        Returns
        -------
        tuple[str, ...]
            Node names.

        """
        return tuple(sorted(_.node_name for _ in self._nodes))

    @property
    def executors(self) -> tuple[ExecutorStructValue, ...]:
        """
        Get executors.

        Returns
        -------
        tuple[ExecutorStructValue, ...]
            Executors.

        """
        return tuple(v.to_value() for v in self._executors)

    @property
    def executor_names(self) -> tuple[str, ...]:
        """
        Get executor names.

        Returns
        -------
        tuple[str, ...]
            Executor names.

        """
        return tuple(sorted(_.executor_name for _ in self._executors))

    @property
    def paths(self) -> tuple[PathStructValue, ...]:
        """
        Get paths.

        Returns
        -------
        tuple[PathStructValue, ...]
            Path struct value.

        """
        return tuple([v.to_value() for v in self._paths])

    @property
    def path_names(self) -> tuple[str, ...]:
        """
        Get path names.

        Returns
        -------
        tuple[str, ...]
            Path names.

        """
        return tuple(sorted(v.path_name for v in self._paths if v.path_name is not None))

    @property
    def communications(self) -> tuple[CommunicationStructValue, ...]:
        """
        Get communications.

        Returns
        -------
        tuple[CommunicationStructValue, ...]
            Communication struct value.

        """
        return tuple(v.to_value() for v in self._communications)

    @property
    def publishers(self) -> tuple[PublisherStructValue, ...]:
        """
        Get publishers.

        Returns
        -------
        tuple[PublisherStructValue, ...]
            Publisher struct value.

        """
        publishers = Util.flatten(_.publishers for _ in self.nodes)
        return tuple(sorted(publishers, key=lambda x: x.topic_name))

    @property
    def subscriptions(self) -> tuple[SubscriptionStructValue, ...]:
        """
        Get subscriptions.

        Returns
        -------
        tuple[SubscriptionStructValue, ...]
            Subscription struct value.

        """
        subscriptions = Util.flatten(_.subscriptions for _ in self.nodes)
        return tuple(sorted(subscriptions, key=lambda x: x.topic_name))

    @property
    def services(self) -> tuple[ServiceStructValue, ...]:
        """
        Get services.

        Returns
        -------
        tuple[ServiceStructValue, ...]
            Service struct value.

        """
        services = Util.flatten(_.services for _ in self.nodes)
        return tuple(sorted(services, key=lambda x: x.service_name))

    @property
    def summary(self) -> Summary:
        """
        Get summary.

        Returns
        -------
        Summary
            Summary about value objects and runtime data objects.

        """
        return Summary({
            'nodes': self.node_names
        })

    def export(self, file_path: str, force: bool = False):
        """
        Architecture export.

        Parameters
        ----------
        file_path : str
            File path.
        force : bool
            Forced specification, by default False.
            If True, a file with the same name will be overwritten if it exists.

        """
        exporter = ArchitectureExporter(
            self.nodes, self.executors, self.paths, force)
        exporter.execute(file_path)

    def search_paths(
        self,
        *node_names: str,
        max_node_depth: int | None = None,
        node_filter: Callable[[str], bool] | None = None,
        communication_filter: Callable[[str], bool] | None = None,
    ) -> list[PathStructValue]:
        """
        Search for paths between specified nodes.

        Parameters
        ----------
        node_names : str
            Specifies the name of the node included in the path to search.
        max_node_depth : int | None
            Max node depth.
        node_filter : Callable[[str], bool] | None
            Node filter.
        communication_filter : Callable[[str], bool] | None
            Communication filter.

        Returns
        -------
        list[PathStructValue]
            Search result path struct value.

        """
        for node_name in node_names:
            if node_name not in self.node_names:
                raise ItemNotFoundError(f'Failed to find node. {node_name}')

        default_depth = 15  # When the depth is 15, the process takes only a few seconds.
        max_node_depth = max_node_depth or default_depth

        # Print message before search
        msg_detail_page = (
            'For details, '
            'see https://tier4.github.io/caret_doc/latest/configuration/inter_node_data_path/.'
        )
        if max_node_depth > default_depth:
            msg = (
                f"Argument 'max_node_depth' greater than {default_depth} is not recommended "
                'because it significantly increases the search time '
                'and the number of returned paths. '
            )
            msg += (
                f'If you are searching for paths that exceeds the depth {default_depth}, '
                'consider specifying an intermediate node. '
            )
            msg += msg_detail_page
            print(msg)

        # Search
        path_searcher = NodePathSearcher(
            tuple(self._nodes),
            tuple(self._communications),
            self._max_callback_construction_order_on_path_searching,
            node_filter,
            communication_filter
        )
        paths = [v.to_value() for v in
                 path_searcher.search(*node_names, max_node_depth=max_node_depth)]

        # Print message after search
        msg = f'A search up to depth {max_node_depth} has been completed. '
        msg += (
            'If the paths you want to measure cannot be found, '
            'consider specifying intermediate nodes. '
        )
        msg += 'Also, if the number of paths is too large, consider filtering node/topic names. '
        msg += msg_detail_page
        print(msg)

        return paths

    @type_check_decorator
    def combine_path(
        self,
        path_left: PathStructValue,
        path_right: PathStructValue
    ) -> PathStructValue:
        """
        Combine path.

        Parameters
        ----------
        path_left : PathStructValue
            Path left.
        path_right : PathStructValue
            Path right.

        Returns
        -------
        PathStructValue:
            Path struct value of combined results.

        """
        def get_node(node_name: str) -> NodeStructValue:
            return self.get_node(node_name)

        def get_communication(
            publish_node_name: str,
            subscribe_node_name: str,
            topic_name: str
        ) -> CommunicationStructValue:
            return self.get_communication(publish_node_name, subscribe_node_name, topic_name)

        combine_path = CombinePath(get_node, get_communication)
        return combine_path.combine(path_left, path_right)

    @staticmethod
    def _verify(nodes: Collection[NodeStruct]) -> None:
        from collections import Counter

        # verify callback parameter uniqueness
        for node in nodes:
            callbacks = node.callbacks
            if callbacks is None:
                continue

            callback_params: list[tuple[str, str | int, str, int]] = []
            for callback in callbacks:
                cb_type = callback.callback_type_name
                symbol = callback.symbol
                # TODO: refactor Add callback_parameter property to CallbackStruct
                cb_param: str | int
                if isinstance(callback, TimerCallbackStruct):
                    cb_param = callback.period_ns
                elif isinstance(callback, SubscriptionCallbackStruct):
                    cb_param = callback.subscribe_topic_name
                elif isinstance(callback, ServiceCallbackStruct):
                    cb_param = callback.service_name
                else:
                    continue
                callback_params.append((cb_type, cb_param, symbol, callback.construction_order))

            counter = Counter(callback_params)

            for uniqueness_violated in [param for param, count in counter.items() if count >= 2]:
                logger.warning(
                    ('Duplicate parameter callback found. '
                     f'node_name: {node.node_name}, '
                     f'callback_type: {uniqueness_violated[0]}'
                     f'period_ns: {uniqueness_violated[1]}'))

    def update_message_context(self, node_name: str, context_type: str,
                               subscribe_topic_name: str, publish_topic_name: str) -> None:
        """
        Update message_context of node_path in "node_name" node.

        Parameters
        ----------
        node_name : str
            name of target node
        context_type : str
            type name of message_context to be added
        subscribe_topic_name : str
            name of subscribe topic of target node_path
        publish_topic_name : str
            name of publish topic of target node_path

        Raises
        ------
        ItemNotFoundError
            Occurs when no items were found.
        MultipleItemFoundError
            Occurs when several items were found.

        """
        node: NodeStruct =\
            Util.find_one(lambda x: x.node_name == node_name, self._nodes)

        if publish_topic_name not in node.publish_topic_names:
            raise ItemNotFoundError('{pub_topic_name} is not found in {node_name}')

        if subscribe_topic_name not in node.subscribe_topic_names:
            raise ItemNotFoundError('{sub_topic_name} is not found in {node_name}')

        context_updater = ContextUpdater(node)
        context_updater.update_message_context(
                                        context_type,
                                        subscribe_topic_name,
                                        publish_topic_name
                                    )
        node.update_node_path(
            NodeValuesLoaded._search_node_paths(
                                node,
                                context_updater.get_message_contexts(),
                                self._max_callback_construction_order_on_path_searching)
                            )

    def insert_publisher_callback(self, node_name: str,
                                  publish_topic_name: str, callback_name: str,
                                  publisher_construction_order: int) -> None:
        """
        Insert association of callback with publisher in "node_name" node.

        Parameters
        ----------
        node_name : str
            name of target node
        publish_topic_name : str
            topic name of target publisher into which callback is inserted
        callback_name : str
            name of callback to be inserted for publisher
        publisher_construction_order : int
            construction order of target publisher

        Raises
        ------
        ItemNotFoundError
            Occurs when no items were found.
        MultipleItemFoundError
            Occurs when several items were found.

        """
        node: NodeStruct = Util.find_one(lambda x: x.node_name == node_name, self._nodes)

        node.insert_publisher_callback(publish_topic_name,
                                       callback_name, publisher_construction_order)

        node.update_node_path(
            NodeValuesLoaded._search_node_paths(
                                node,
                                ContextUpdater(node).get_message_contexts(),
                                self._max_callback_construction_order_on_path_searching)
                            )

    def insert_variable_passing(self, node_name: str,
                                callback_name_write: str, callback_name_read: str) -> None:
        """
        Insert variable_passing in "node_name" node.

        Parameters
        ----------
        node_name : str
            name of target node
        callback_name_write : str
            name of write callback to be inserted in variable_passing
        callback_name_read : str
            name of read callback to be inserted in variable_passing

        Raises
        ------
        ItemNotFoundError
            Occurs when no items were found.
        MultipleItemFoundError
            Occurs when several items were found.

        """
        node: NodeStruct = Util.find_one(lambda x: x.node_name == node_name, self._nodes)

        node.insert_variable_passing(callback_name_write, callback_name_read)

        node.update_node_path(
            NodeValuesLoaded._search_node_paths(
                                node,
                                ContextUpdater(node).get_message_contexts(),
                                self._max_callback_construction_order_on_path_searching)
                            )

    def remove_publisher_callback(self, node_name: str,
                                  publish_topic_name: str, callback_name: str,
                                  publisher_construction_order: int) -> None:
        """
        Remove association of callback with publisher in "node_name" node.

        Parameters
        ----------
        node_name : str
            name of target node
        publish_topic_name : str
            topic name of target publisher from which callback is removed
        callback_name : str
            name of callback to be removed for publisher
        publisher_construction_order : int
            construction order of target publisher

        Raises
        ------
        ItemNotFoundError
            Occurs when no items were found.
        MultipleItemFoundError
            Occurs when several items were found.

        """
        node: NodeStruct = Util.find_one(lambda x: x.node_name == node_name, self._nodes)

        node.remove_publisher_and_callback(publish_topic_name,
                                           callback_name, publisher_construction_order)

        node.update_node_path(
            NodeValuesLoaded._search_node_paths(
                                node,
                                ContextUpdater(node).get_message_contexts(),
                                self._max_callback_construction_order_on_path_searching)
                            )

    def remove_variable_passing(self, node_name: str,
                                callback_name_write: str, callback_name_read: str) -> None:
        """
        Remove variable_passing in "node_name" node.

        Parameters
        ----------
        node_name : str
            name of target node
        callback_name_write : str
            name of write callback to be removed from variable_passing
        callback_name_read : str
            name of read callback to be removed from variable_passing

        Raises
        ------
        ItemNotFoundError
            Occurs when no items were found.
        MultipleItemFoundError
            Occurs when several items were found.

        """
        node: NodeStruct = Util.find_one(lambda x: x.node_name == node_name, self._nodes)

        node.remove_variable_passing(callback_name_write, callback_name_read)

        callback_read: CallbackStructValue = \
            Util.find_one(lambda x: x.callback_name == callback_name_read, self.callbacks)
        callback_write: CallbackStructValue = \
            Util.find_one(lambda x: x.callback_name == callback_name_write, self.callbacks)

        if callback_read.publish_topics:
            context_updater = ContextUpdater(node)
            for publish_topic in callback_read.publish_topics:
                if callback_write.subscribe_topic_name and publish_topic is not None:
                    context_updater.remove_callback_chain(
                        callback_write.subscribe_topic_name,
                        callback_write.construction_order,
                        publish_topic.topic_name,
                        publish_topic.construction_order)
            node.update_node_path(
                NodeValuesLoaded._search_node_paths(
                                    node,
                                    context_updater.get_message_contexts(),
                                    self._max_callback_construction_order_on_path_searching)
                                )

    def rename_callback(self, src: str, dst: str) -> None:
        """
        Update callback name from "src" to "dst" in architecture.

        Parameters
        ----------
        src : str
            current callback name
        dst : str
            updated callback name

        Raises
        ------
        ItemNotFoundError
            Occurs when no items were found.

        """
        cb_s: list[CallbackStruct] =\
            Util.flatten(cb_g.callbacks for cb_g in
                         Util.flatten([e.callback_groups for e in self._executors]))
        c: CallbackStruct = Util.find_similar_one(src, cb_s, lambda x: x.callback_name)
        c.callback_name = dst

    def rename_node(self, src: str, dst: str) -> None:
        """
        Update node name from "src" to "dst" in architecture.

        Parameters
        ----------
        src : str
            current node name
        dst : str
            updated node name

        """
        for n in self._nodes:
            n.rename_node(src, dst)

        for e in self._executors:
            e.rename_node(src, dst)

        for c in self._communications:
            c.rename_node(src, dst)

    def rename_path(self, src: str, dst: str) -> None:
        """
        Update path name from "src" to "dst" in architecture.

        Parameters
        ----------
        src : str
            current path name
        dst : str
            updated path name

        Raises
        ------
        ItemNotFoundError
            Occurs when no items were found.

        """
        p: PathStruct = Util.find_similar_one(src, self._paths, lambda x: x.path_name)
        p.path_name = dst

    def rename_executor(self, src: str, dst: str) -> None:
        """
        Update executor name from "src" to "dst" in architecture.

        Parameters
        ----------
        src : str
            current executor name
        dst : str
            updated executor name

        Raises
        ------
        ItemNotFoundError
            Occurs when no items were found.

        """
        e: ExecutorStruct = Util.find_similar_one(src, self._executors, lambda x: x.executor_name)
        e.executor_name = dst

    def rename_topic(self, src: str, dst: str) -> None:
        """
        Update topic name from "src" to "dst" in architecture.

        Parameters
        ----------
        src : str
            current topic name
        dst : str
            updated topic name

        """
        for n in self._nodes:
            n.rename_topic(src, dst)

        for e in self._executors:
            e.rename_topic(src, dst)

        for c in self._communications:
            c.rename_topic(src, dst)

    @staticmethod
    def diff_node_names(
        left_arch: Architecture,
        right_arch: Architecture
    ) -> tuple[tuple[str, ...], tuple[str, ...]]:
        """
        Compare two architecture objects and return the difference of nodes name.

        Parameters
        ----------
        left_arch : Architecture
            Architecture object
        right_arch : Architecture
            Architecture object

        Returns
        -------
        tuple[tuple[str,...], tuple[str,...]]
            Returns node names that exist only in the respective architectures.

        """
        return DiffArchitecture(left_arch, right_arch).diff_node_names()

    @staticmethod
    def diff_topic_names(
        left_arch: Architecture,
        right_arch: Architecture
    ) -> tuple[tuple[str, ...], tuple[str, ...]]:
        """
        Compare two architecture objects and return the difference of pub/sub topic names.

        Parameters
        ----------
        left_arch : Architecture
            Architecture object
        right_arch : Architecture
            Architecture object

        Returns
        -------
        tuple[tuple[str,...], tuple[str,...]]
            Returns pub/sub topic names that exist only in the respective architectures.

        """
        return DiffArchitecture(left_arch, right_arch).diff_topic_names()

    @staticmethod
    def diff_node_pubs(
        left_node: NodeStructValue,
        right_node: NodeStructValue
    ) -> tuple[tuple[str, ...], tuple[str, ...]]:
        """
        Compare two nodes of architecture objects and return the difference of publish topic names.

        Parameters
        ----------
        left_node : NodeStructValue
            Node in architecture
        right_node : NodeStructValue
            Node in architecture

        Returns
        -------
        tuple[tuple[str,...], tuple[str,...]]
            Returns publish topic names that exist only in the respective nodes.

        """
        return DiffNode(left_node, right_node).diff_node_pubs()

    @staticmethod
    def diff_node_subs(
        left_node: NodeStructValue,
        right_node: NodeStructValue
    ) -> tuple[tuple[str, ...], tuple[str, ...]]:
        """
        Compare two nodes of architecture objects and return the difference of \
        subscribe topic names.

        Parameters
        ----------
        left_node : NodeStructValue
            Node in architecture
        right_node : NodeStructValue
            Node in architecture

        Returns
        -------
        tuple[tuple[str,...], tuple[str,...]]
            Returns subscribe topic names that exist only in the respective nodes.

        """
        return DiffNode(left_node, right_node).diff_node_subs()


class ContextUpdater:
    """MessageContext updater of NodeStruct."""

    def __init__(self, node: NodeStruct) -> None:
        contexts = [path.message_context for path in node.paths]
        self._node = node
        self._contexts = \
            [context.to_dict() for context in contexts if context is not None]

    def update_message_context(self, context_type: str,
                               subscribe_topic_name: str, publish_topic_name: str) -> None:
        """
        Update message context.

        Parameters
        ----------
        context_type : str
            type name of message_context to be added
        subscribe_topic_name : str
            name of subscribe topic of target node_path
        publish_topic_name : str
            name of publish topic of target node_path

        """
        for context in self._contexts:
            if (context['subscription_topic_name'], context['publisher_topic_name']) ==\
               (subscribe_topic_name, publish_topic_name):
                context['context_type'] = context_type
        for path in self._node.paths:
            if path.message_context is not None:
                # already processed by the above self._contexts process
                continue
            else:
                if (path.subscribe_topic_name, path.publish_topic_name) ==\
                        (subscribe_topic_name, publish_topic_name):
                    self._contexts.append({
                        'context_type': context_type,
                        'subscription_topic_name': subscribe_topic_name,
                        'publisher_topic_name': publish_topic_name,
                        'publisher_construction_order': path.publisher_construction_order,
                        'subscription_construction_order': path.subscription_construction_order
                    })

    def remove_callback_chain(
        self,
        subscribe_topic_name: str,
        subscription_construction_order: int,
        publish_topic_name: str,
        publisher_construction_order: int
    ) -> None:
        """
        Remove callback chain.

        Parameters
        ----------
        subscribe_topic_name : str
            topic name of target subscription from which callback is removed
        subscription_construction_order : int
            construction order of target subscription
        publish_topic_name : str
            topic name of target publisher from which callback is removed
        publisher_construction_order : int
            construction order of target publisher

        """
        self._contexts = [
            context for context in self._contexts
            if (context['subscription_topic_name'],
                context.get('subscription_construction_order', 0),
                context['publisher_topic_name'],
                context.get('publisher_construction_order', 0),
                context['context_type']) != (subscribe_topic_name,
                                             subscription_construction_order,
                                             publish_topic_name,
                                             publisher_construction_order,
                                             'callback_chain')
        ]

    def get_message_contexts(self) -> Sequence[dict]:
        return self._contexts


# NOTE: DiffArchitecture may be changed when it is refactored.
class DiffArchitecture:

    def __init__(
        self,
        left_arch: Architecture,
        right_arch: Architecture
    ):
        self._left_arch = left_arch
        self._right_arch = right_arch

    def diff_node_names(self) -> tuple[tuple[str, ...], tuple[str, ...]]:
        """
        Compare two architecture objects and return the difference of nodes name.

        Returns
        -------
        tuple[tuple[str,...], tuple[str,...]]
            Returns node names that exist only in the respective architectures.

        """
        set_left_node_names = set(self._left_arch.node_names)
        set_right_node_names = set(self._right_arch.node_names)
        common_node_names = set_left_node_names & set_right_node_names
        left_only_names = tuple(set_left_node_names - common_node_names)
        right_only_names = tuple(set_right_node_names - common_node_names)
        return left_only_names, right_only_names

    def diff_topic_names(self) -> tuple[tuple[str, ...], tuple[str, ...]]:
        """
        Compare two architecture objects and return the difference of pub/sub topic names.

        Returns
        -------
        tuple[tuple[str,...], tuple[str,...]]
            Returns pub/sub topic names that exist only in the respective architectures.

        """
        set_left_topics = set(self._left_arch.topic_names)
        set_right_topics = set(self._right_arch.topic_names)
        common_node_topics = set_left_topics & set_right_topics
        left_only_topics = tuple(set_left_topics - common_node_topics)
        right_only_topics = tuple(set_right_topics - common_node_topics)
        return left_only_topics, right_only_topics
