# Copyright (C) 2010  Brian Parma (execrable@gmail.com)
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
#
# main.py

from twisted.internet import gtk2reactor
gtk2reactor.install()

import os
import gtk
import gobject
import logging
import math
from gtk import glade
from twisted.internet import reactor, defer
from twisted.python import failure, log, util
from twisted.spread import pb
from twisted.cred.credentials import UsernamePassword
from twisted.internet import error as netError

from .. import util
from ..interface import Interface
from ..mods.chatter import ChatterBox

logger = logging.getLogger(__name__)

def find_iter(model, obj, col):

    for row in model:
        if row[col] == obj:
            return row.iter

    return None

def show_message(text):
    '''helper function for showing a MessageDialog popup'''
    dlg = gtk.MessageDialog(type=gtk.MESSAGE_INFO, 
                            buttons=gtk.BUTTONS_OK, 
                            message_format=text)
    dlg.connect('response', lambda *x: dlg.destroy())
    dlg.show_all()

class TextBufferHandler(logging.Handler):
    '''handler for logging to a GtkTextBuffer'''
    def __init__(self, buffer):
        self.buf = buffer
        logging.Handler.__init__(self)

    def emit(self, record):
        self.buf.insert(self.buf.get_end_iter(), '{1} : {0} : {2}\n'
                                        .format(record.name,
                                                record.levelname,
                                                record.message))

class NetPage(object):
    '''
        A class representing a network's notebook page. 
    '''
    def __init__(self, net, nb_label=None):

        self.net = net
        self.nb_label = nb_label

        self.widget = gtk.VBox()
        self.label = gtk.Label()
        self.label_eb = gtk.EventBox()

        self.label.set_justify(gtk.JUSTIFY_CENTER)
        self.update_label()

        # list store: name, ip, peer_id, network object
        self.model = gtk.ListStore(str, str, str, object)

        self.view = gtk.TreeView(self.model)

        cr = gtk.CellRendererText()
        col = gtk.TreeViewColumn('Name',cr,text=0)
        self.view.append_column(col)

        cr = gtk.CellRendererText()
        col = gtk.TreeViewColumn('IP',cr,text=1)
        self.view.append_column(col)

        self.label_eb.add(self.label)
        self.widget.pack_start(self.label_eb, False, False, 0)
        self.widget.pack_end(self.view, True, True, 0)

        self.selection = self.view.get_selection()
        
        logger.debug('NetPage added for {0}'.format(net.name))

    def update_label(self):
        '''refresh text label on network page and tab'''
        if self.net.enabled:
            if self.net.is_running:
                status = 'online'
            else:
                status = 'offline'
        else:
            status = 'disabled'

        self.label.set_markup('<b>{0}</b>\n<i>{1}</i>\n{2}'
                            .format(self.net.username,self.net.ip,status))

        if self.nb_label is not None:
            if self.net.is_running:
                self.nb_label.set_markup('<b>{0}</b>'.format(self.net.name))
            else:
                self.nb_label.set_markup('<i>{0}</i>'.format(self.net.name))
        else:
            self.nb_label.set_markup('<i><s>{0}</i></s>'.format(self.net.name))


    def clear(self):
        self.model.clear()

    def add_peer(self, peer):
        iter = find_iter(self.model, str(peer.id), 2)

        if iter is None:
            self.model.append([peer.name,peer.vip_str,peer.id, peer])

            logger.info('added peer {0}'.format(peer.name))

        else:
            row = self.model[iter]
            row[0] = peer.name
            row[1] = peer.vip_str
            row[2] = str(peer.id)
            row[3] = peer

            logger.info('updated peer information for {0}'.format(peer.name))

    def remove_peer(self, peer):
        iter = find_iter(self.model, str(peer.id), 2)

        if iter is not None:
            self.model.remove(iter)

            logger.info('removed peer {0}'.format(peer.name))

class MainWin(object):
    def __init__(self, iface):

        self.builder = gtk.Builder()
        self.builder.add_from_file('pylans/gui/main.ui')

        # get objects from xml
        self.get_objects()

        # a dict to store the pages in
        self._net_page = {}

        self.builder.connect_signals(self)
#        self._selection = self._peer_treeview.get_selection()

        self._main_window.set_default_size(200,400)

        # logging
        handler = TextBufferHandler(gtk.TextBuffer())
        logging.getLogger().addHandler(handler)
        self._log_buffer = handler.buf

        #Events
        iface.peer_added += self._add_peer
        iface.peer_removed += self._remove_peer
        iface.peer_changed += self._add_peer
        iface.network_started += self._network_on
        iface.network_stopped += self._network_off
        iface.network_enabled += self._network_enabled
        iface.network_disabled += self._network_disabled
        iface.network_created += self._add_network
        iface.network_removed += self._remove_network
        iface.network_changed += lambda nw: (nw.id in self._net_page) and \
                                            self._net_page[nw.id].update_label()
        iface.message_received += self._message
        self._main_window.connect('delete-event', lambda *x: reactor.stop())

        self._main_window.show_all()

        nws = iface.get_network_list()

        self.__placeholder = None

        # This just makes it so disabled networks get put at the end
        # and sort by name
        nws.sort(key=lambda x: (not x.enabled, x.name))
        if len(nws) > 0:
            for nw in nws:
                self._add_network(None, nw)
        else:
            self._check_empty()

        self.iface = iface

    @property
    def _placeholder(self):
        '''lazily generate empty placeholder'''
        if self.__placeholder is None:
            wgt = gtk.Alignment(xalign=0.5, yalign=0.5)
            wgt.add(gtk.Label("No Networks."))
            wgt.show_all()
            self.__placeholder = wgt
            
        return self.__placeholder

    def _get_np(self, widget):
        '''find a netpage in the dict by its container widget'''
        for np in self._net_page.values():
            if np.widget is widget:
                return np
        return None

    def get_objects(self):
        '''get objects from GtkBuilder'''
        objects = ('main_window','name_label','peer_menu',
                    'network_menu','main_menu','netbook')
        go = self.builder.get_object
        for obj_name in objects:
            setattr(self, "_" + obj_name, go(obj_name))



#### Event Handlers

    def on_menu_button_event(self, widget, event):
        '''menu buton clicked'''
        if event.type == gtk.gdk.BUTTON_PRESS:
            def menu_pos(menu, user_data=None):
                r = widget.get_allocation()
                (x,y) = widget.window.get_origin()
                return (x+r.x, y+r.y, False)

            self._main_menu.popup(None, None, menu_pos, 
                                    event.button, event.time)

    def on_exit(self, *x):
        '''exit clicked'''
        reactor.callFromThread(reactor.stop)

    def on_view_log(self, widget):
        '''open up textview widget to display log'''
        builder = gtk.Builder()
        builder.add_from_file('pylans/gui/main.ui')

        win = builder.get_object('log_window')
        leb = builder.get_object('log_level_eb')
        tv = builder.get_object('log_view')
        bclose = builder.get_object('close_button')
        bclear = builder.get_object('clear_button')

        tv.set_buffer(self._log_buffer)

        cb = gtk.combo_box_new_text()
        leb.add(cb)
        cb.append_text('DEBUG')
        cb.append_text('INFO')
        cb.append_text('WARNING')
        cb.append_text('ERROR')
        cb.append_text('CRITICAL')

        cb.set_active(self.iface.log_level/10 - 1)

        def do_changed(*args):
            idx = cb.get_active()
            self.iface.log_level = (idx + 1)*10

        cb.connect('changed', do_changed)

        bclear.connect('clicked', 
                        lambda *x: self._log_buffer.delete(
                                            self._log_buffer.get_start_iter(),
                                            self._log_buffer.get_end_iter()))
                                            
        bclose.connect('clicked', lambda *x: win.destroy())

        win.set_default_size(500,400)
        win.show_all()


    def on_rename(self, *x):
        '''rename clicked'''
        n = self._netbook.get_current_page()
        np = self._get_np(self._netbook.get_nth_page(n))
        if np is not None:
            net = np.net
            
            # build dialog
            dlg = gtk.MessageDialog(self._main_window, 
                                    type=gtk.MESSAGE_QUESTION,
                                    buttons=gtk.BUTTONS_OK_CANCEL,
                message_format='Enter new name for network \'{0}\':'
                                                    .format(net.name))
                                                    
            dlg.set_title('Rename Network')
            entry = gtk.Entry()
            hbox = gtk.HBox()
            hbox.pack_start(gtk.Label('Name:') ,False, 5, 5)
            hbox.pack_end(entry)
            dlg.vbox.pack_end(hbox, True, True, 0)
            dlg.set_default_response(gtk.RESPONSE_OK)
            entry.set_activates_default(True)
            entry.set_text(net.name)

            def response(dialog, rid):
                '''response callback'''
                if rid == gtk.RESPONSE_OK:
                    self.iface.set_network_name(entry.get_text(), net)
                dialog.destroy()

            dlg.connect('response',response)
            dlg.show_all()

    def on_delete(self, *x):
        '''delete clicked'''
        n = self._netbook.get_current_page()
        np = self._get_np(self._netbook.get_nth_page(n))
        if np is not None:
            net = np.net
            dlg = gtk.MessageDialog(self._main_window, 
                                    type=gtk.MESSAGE_QUESTION,
                                    buttons=gtk.BUTTONS_YES_NO,
                        message_format='Really delete network \'{0}\'?'
                                                    .format(net.name))
                                                    
            dlg.set_title('Delete Network')

            def response(dialog, rid):
                '''response callback'''
                dialog.destroy()
                if rid == gtk.RESPONSE_YES:
                    self.iface.delete_network(net)

            dlg.connect('response',response)
            dlg.show_all()

    def on_create(self, *x):
        '''create network clicked'''
        builder = gtk.Builder()
        builder.add_from_file('pylans/gui/main.ui')

        dlg = builder.get_object('new_dialog')
        
        dlg.set_default_size(400, dlg.get_size()[1])

        # Basic
        name_entry = builder.get_object('name_entry')
        alias_entry = builder.get_object('alias_entry')
        key_entry = builder.get_object('key_entry')
        address_entry = builder.get_object('address_entry')
        port_spinbox = builder.get_object('port_spinbox')

        # Advanced
        enabled_cb = builder.get_object('enabled_cb')
        use_bt = builder.get_object('use_bt_cb')
        bt_url = builder.get_object('bt_url_entry')
        ping_interval = builder.get_object('ping_spinbox')
        meb = builder.get_object('mode_eb')

        mcb = gtk.combo_box_new_text()
        meb.add(mcb)
        mcb.append_text('TAP')
        mcb.append_text('TUN')


        # Default values
        name_entry.set_text('new_network')
        alias_entry.set_text('user')
        key_entry.set_text(os.urandom(56).encode('base64'))
        address_entry.set_text('10.1.1.1/24')
        port_spinbox.set_value(8500)

        enabled_cb.set_active(True)
        use_bt.set_active(False)
        bt_url.set_text('')
        ping_interval.set_value(5)
        mcb.set_active(0)


        def response(dialog, rid):
            '''dialog response'''
            if rid == gtk.RESPONSE_OK:
                name = name_entry.get_text()
                
                # check for name collision
                if name in self.iface.get_network_names():
                    show_message('A network with that name already exists')
                    return

                alias = alias_entry.get_text()
                key = key_entry.get_text()
                
                # don't allow empty key
                if key == '':
                    key = os.urandom(56)
                    
                address = address_entry.get_text()
                port = int(port_spinbox.get_value())
                mode = 'TAP' if mcb.get_active() == 0 else 'TUN'
                enabled = enabled_cb.get_active()

                # create network
                nw = self.iface.create_new_network(name, username=alias,
                                                    key_str=key, port=port,
                                                    address=address,
                                                    enabled=enabled, mode=mode)
    
                # set some advanced settings
                self.iface.set_network_ping_interval(ping_interval.get_value(), 
                                                    nw)
                self.iface.set_network_use_tracker(use_bt.get_active(), nw)
                if bt_url.get_text() != '':
                    self.iface.set_network_tracker_url(bt_url.get_text(), nw)


            dialog.destroy()

        dlg.connect('response',response)
        dlg.show_all()

    def on_network_get_info(self, widget):
        '''get info on network by it's notebook widget'''
        n = self._netbook.get_current_page()
        np = self._get_np(self._netbook.get_nth_page(n))
        if np is not None:
            net = np.net

            builder = gtk.Builder()
            builder.add_from_file('pylans/gui/main.ui')

            dlg = builder.get_object('new_dialog')
            dlg.set_default_size(400,dlg.get_size()[1])

            # Basic
            name_entry = builder.get_object('name_entry')
            alias_entry = builder.get_object('alias_entry')
            key_entry = builder.get_object('key_entry')
            address_entry = builder.get_object('address_entry')
            port_spinbox = builder.get_object('port_spinbox')
            # Advanced
            enabled_cb = builder.get_object('enabled_cb')
            use_bt = builder.get_object('use_bt_cb')
            bt_url = builder.get_object('bt_url_entry')
            ping_interval = builder.get_object('ping_spinbox')
            meb = builder.get_object('mode_eb')
            nb = builder.get_object('net_notebook')

            mcb = gtk.combo_box_new_text()
            meb.add(mcb)
            mcb.append_text('TAP')
            mcb.append_text('TUN')


            # set values
            name_entry.set_text(net.name)
            alias_entry.set_text(net.username)
            key_entry.set_text(net.key_str)
            address_entry.set_text(net.virtual_address)
            port_spinbox.set_value(net.port)

            enabled_cb.set_active(net.enabled)
            bt_url.set_text(self.iface.get_network_setting('tracker', 
                                                            net, default=''))
            ping_interval.set_value(
                        self.iface.get_network_setting('ping_interval', 
                                                        net, default=5))
            mcb.set_active(net.adapter_mode == 'TUN')

            # add new tabs
            da = gtk.DrawingArea()
            nb.insert_page(da, gtk.Label('Map'), 0)
            nb.set_current_page(0)

            def response(dialog, rid):
                '''dialog response callback'''
                if rid == gtk.RESPONSE_OK:
                    net.name = name_entry.get_text()
                    net.username = alias_entry.get_text()
                    net.key_str = key_entry.get_text()
                    net.virtual_address = address_entry.get_text()
                    net.port = int(port_spinbox.get_value())
                    net.adapter_mode = 'TAP' if mcb.get_active() == 0 else 'TUN'
                    net.enabled = enabled_cb.get_active()

                    # do BT and ping stuff?
                    self.iface.set_network_setting('ping_interval',
                                                ping_interval.get_value(), net)
                    self.iface.set_network_setting('use_tracker', 
                                                use_bt.get_active(), net)

                    if bt_url.get_text() != '':
                        self.iface.set_network_setting('tracker', 
                                                       bt_url.get_text(), net)


                dialog.destroy()


            # Drawing stuff
            def expose(widget, event):
                '''expose callback for plot'''
                ctx = widget.window.cairo_create()
                ctx.rectangle(event.area.x,event.area.y,
                                event.area.width,event.area.height)
                ctx.clip()

                rec = widget.get_allocation()
                cx = (rec.width)/2.
                cy = (rec.height)/2. - 15
                r = min(rec.width,rec.height)/2. - 20

                # helpers
                def draw_text(text):
                    dy = 24
                    dt = 10
                    tx, ty, tw, th = ctx.text_extents(text)[:4]
                    ctx.set_source_rgba(1,1,1,0.7)
                    ctx.rectangle(x - tw/2. - dt/2., y + dy + ty - dt/2., 
                                        tw + dt, th + dt)
                    ctx.fill_preserve()
                    ctx.set_source_rgba(0,0,0,1)
                    ctx.stroke()
                    ctx.move_to(x-tw/2., y+dy)
                    ctx.show_text(text)
                    ctx.stroke()

                # get peer map
                if net.is_running:
                    _map = net.router.pm.peer_map
                    _map[net.router.pm._self.id] = net.router.pm.peer_list
                    dth = 2*math.pi/len(_map)
                else:
                    _map = []
                    x, y = cx, cy
                    draw_text('network offline')
                                        
                loc = {}
                
                # Determine Locations
                for i,p in enumerate(_map):
                    t = dth*i
                    x = cx+math.sin(t)*r
                    y = cy+math.cos(t)*r
                    loc[p] = (x,y)
                    i += 1

                # Draw Lines
                ctx.set_source_rgb(0,0,0)
                ctx.set_line_width(1)
                for p in _map:
                    for pc in _map[p]:
                        if pc in _map:
                            if _map[p][pc].is_direct:
                                ctx.set_dash(())
                            else:
                                ctx.set_dash((6.,8.))
                            ctx.move_to(*loc[p])
                            ctx.line_to(*loc[pc])
                            ctx.stroke()

                # draw text boxes
                ctx.set_dash(())
                for p in _map:
                    x, y = loc[p][0],loc[p][1]

                    # draw mark
                    if net.router.pm._self.id == p:
                        ctx.set_source_rgb(.4,.4,.4)
                    elif net.router.pm[p].is_direct:
                        ctx.set_source_rgb(0,0,1)
                    else:
                        ctx.set_source_rgb(0,1,0)

                    ctx.arc(x, y, 6, 0, 2*math.pi)
                    ctx.fill_preserve()
                    ctx.set_source_rgb(0,0,0)
                    ctx.stroke()

                    draw_text(net.router.pm[p].name)

            da.connect('expose-event', expose)
            dlg.connect('response',response)
            dlg.show_all()


    def on_peer_get_info(self, widget):
        '''get peer info by selected widget'''
        n = self._netbook.get_current_page()
        np = self._get_np(self._netbook.get_nth_page(n))
        model, iter = np.selection.get_selected()

        if iter is not None:
            peer = model.get_value(iter, 3)
            print 'PEER INFO:',peer.name,peer.id,peer.vip_str #TODO


    def on_network_connect_peer(self, widget):
        '''connect clicked'''
        n = self._netbook.get_current_page()
        np = self._get_np(self._netbook.get_nth_page(n))
        if np is not None:
            net = np.net

            # get address
            def get_address(dialog, responseid, entry):
                '''parse response for address'''
                if responseid == gtk.RESPONSE_OK:
                    txt = entry.get_text()
                    addr, port = txt.split(':')
                    port = int(port) if port != '' else 8500
                    addr = (addr, port)
                    self.iface.connect_to_address(addr, net)
                dialog.destroy()

            time = None
            dialog = gtk.MessageDialog(
                        None,
                        gtk.DIALOG_MODAL | gtk.DIALOG_DESTROY_WITH_PARENT,
                        gtk.MESSAGE_QUESTION,
                        gtk.BUTTONS_OK,
                        None)

            dialog.set_title("Connect to address...")
            dialog.set_markup('Enter address:')
            dialog.format_secondary_markup('Accepts input of the form: \
                                             &lt;address&gt;:&lt;port&gt;')
            hbox = gtk.HBox(False, 0)
            hbox.pack_start(gtk.Label('Address: '), False, 5, 5)
            entry = gtk.Entry()
            entry.connect('activate', lambda *x: dialog.response(gtk.RESPONSE_OK))
            hbox.pack_end(entry)
            dialog.vbox.pack_end(hbox, True, True, 0)
            dialog.show_all()
            dialog.connect('response', get_address, entry)


    def on_peer_copy_ip(self, widget):
        '''copy ip of selected peer'''
        n = self._netbook.get_current_page()
        np = self._get_np(self._netbook.get_nth_page(n))
        model, iter = np.selection.get_selected()

        if iter is not None:
            peer = model.get_value(iter, 3)
            clip = gtk.clipboard_get()
            clip.set_text(peer.vip_str)

    def on_peerlist_click(self, widget, event, np):
        '''peerlist click handler; shows context menu'''
        if event.button == 3:
            x, y = int(event.x), int(event.y)
            path_info = widget.get_path_at_pos(x, y)
            if path_info is not None:
                path, col, cx, cy = path_info
                widget.grab_focus()
                widget.set_cursor(path, col, 0)

                self._peer_menu.popup(None, None, None, 
                                      event.button, event.time)

    def on_notebook_click(self, widget, event, np):
        '''netbook click handler; shows context menu'''
        if event.button == 3:
            n = self._netbook.page_num(np.widget)
            self._netbook.set_current_page(n)
            self._network_menu.popup(None, None, None, 
                                     event.button, event.time)


    def on_network_toggle_online(self, widget):
        '''toggle current network online/offline'''
        n = self._netbook.get_current_page()
        np = self._get_np(self._netbook.get_nth_page(n))
        if np is not None:
            net = np.net
            if net.is_running:
                logger.info('stopping network {0}'.format(net.name))
                net.stop()

            else:
                logger.info('starting network {0}'.format(net.name))
                net.start()


    def on_network_toggle_enabled(self, widget):
        '''toggle current network enabled/disabled'''
        n = self._netbook.get_current_page()
        np = self._get_np(self._netbook.get_nth_page(n))
        if np is not None:
            net = np.net
            if net.enabled:
                self.iface.disable_network(net)

                logger.info('disabling network {0}'.format(net.name))
            else:
                self.iface.enable_network(net)

                logger.info('enabling network {0}'.format(net.name))

    def _check_empty(self):
        '''add or remove the empty network placeholder'''
        if len(self._netbook) == 0:
            # notebook empty
            if self._netbook.page_num(self._placeholder) == -1:
                self._netbook.append_page(self._placeholder, None)
                self._netbook.set_show_tabs(False)
        else:
            # notebook not empty
            j = self._netbook.page_num(self._placeholder)
            if j >= 0:
                self._netbook.remove_page(j)
                self._netbook.set_show_tabs(True)

    def _add_network(self, mgr, nw):
        '''generate and add new network notebook page'''
        if nw is not None and nw.id not in self._net_page:

            lab = gtk.Label(nw.name)
            lab.set_angle(270)
            np = NetPage(nw, lab)
            self._net_page[nw.id] = np

            # use an eventbox to capture events for apopup menu
            eb = gtk.EventBox()
            eb.add(lab)
            eb.connect('button-press-event', self.on_notebook_click, np)
            np.label_eb.connect('button-press-event', self.on_notebook_click, np)
            np.view.connect('button-press-event', self.on_peerlist_click, np)
            self._netbook.append_page(np.widget, eb)
            self._netbook.set_tab_reorderable(np.widget, True)
            np.widget.show_all()
            eb.show_all()
            
        self._check_empty()
            
    def _remove_network(self, mgr, nw):
        '''remove network's notebook page'''
        if nw.id in self._net_page:
            np = self._net_page[nw.id]
            self._netbook.remove_page(self._netbook.page_num(np.widget))
            del self._net_page[nw.id]

        self._check_empty()

    def _add_peer(self, net, peer):
        '''add peer to network page'''
        self._net_page[net.id].add_peer(peer)


    def _remove_peer(self, net, peer):
        '''remove peer from network page'''
        self._net_page[net.id].remove_peer(peer)

    def _network_on(self, net):
        '''network online event handler'''
        self._add_network(None, net)
        self._net_page[net.id].update_label()

        logger.info('network {0} online'.format(net.name))

    def _network_off(self, net):
        '''network offline event handler'''
        self._net_page[net.id].clear()
        self._net_page[net.id].update_label()

        logger.info('network {0} offline'.format(net.name))

    def _network_enabled(self, net):
        '''network enabled event handler'''
        self._net_page[net.id].update_label()

        logger.info('network {0} online'.format(net.name))

    def _network_disabled(self, net):
        '''network disabled event handler'''
        self._net_page[net.id].clear()
        self._net_page[net.id].update_label()

        logger.info('network {0} disabled'.format(net.name))

    def _message(self, net, peer, msg):
        '''message event handler'''
        print 'msg',net, peer, msg



def main():
#    import signal, traceback
#    def do_sigup(*x):
#        traceback.print_stack()
#    signal.signal(signal.SIGHUP, do_sigup)

    iface = Interface()

    mw = MainWin(iface)
    iface.start_all_networks()

    reactor.run()

if __name__ == '__main__':
    main()
