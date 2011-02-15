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

import gtk
import gobject
import uuid
import logging
from gtk import glade
from twisted.internet import reactor, defer
from twisted.python import failure, log, util
from twisted.spread import pb
from twisted.cred.credentials import UsernamePassword
from twisted.internet import error as netError

import util
from interface import Interface
from chatter import ChatterBox

logger = logging.getLogger(__name__)

def find_iter(model, obj, col):

    for row in model:
        if row[col] == obj:
            return row.iter
        
    return None


class NetPage:
    def __init__(self, net, nb_label=None):
        
        self.net = net
        self.widget = gtk.VBox()
        self.label = gtk.Label()
        self.label_eb = gtk.EventBox()
        self.nb_label = nb_label

        self.update_label()        
        self.label.set_justify(gtk.JUSTIFY_CENTER)
        
        # list store: name, ip, peer_id
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
        
    def update_label(self):
        if self.net.enabled:
            if self.net.is_running:
                status = 'online'
            else:
                status = 'offline'
        else:
            status = 'disabled'
        
        self.label.set_markup('<b>{0}</b>\n<i>{1}</i>\n{2}'.format(self.net.username,self.net.ip,status))
        
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

class MainWin:
    def __init__(self, iface):

        self.builder = gtk.Builder()
        self.builder.add_from_file('../gui/main.ui')

        # get objects from xml
        self.get_objects()
        
        # a dict to store the pages in
        self._net_page = {}

        self.builder.connect_signals(self)
#        self._selection = self._peer_treeview.get_selection()
        
        self._main_window.resize(200,400)
        self._main_window.connect('delete-event', lambda *x: reactor.stop())
        self._main_window.show_all()
        
#        nw = iface.get_network_list()[0]
#        self._name_label.set_text('%s - %s' % (nw.username, nw.virtual_ip))
        
        
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
        iface.message_received += self._message
        
        nws = iface.get_network_list()
        
        # This just makes it so disabled networks get put at the end
        en = []
        dn = []
        for nw in nws:
            if nw.enabled:
                en.append(nw)
            else:
                dn.append(nw)
        for nw in (en+dn):
            self._add_network(nw)
#            if nw.enabled:
#                self._peer_model.append(None, [nw, "<b>"+nw.name+"</b>", ''])
#            else:
#                self._peer_model.append(None, [nw, "<i>"+nw.name+"</i>", ''])
        
        self.iface = iface

    def _get_np(self, widget):
        for np in self._net_page.values():
            if np.widget is widget:
                return np
        return None

    def get_objects(self):
        objects = ('main_window','name_label','peer_menu','network_menu','netbook')
        go = self.builder.get_object
        for obj_name in objects:
            setattr(self, "_" + obj_name, go(obj_name))

    def on_network_get_info(self, widget):
        n = self._netbook.get_current_page()
        np = self._get_np(self._netbook.get_nth_page(n))
        if np is not None:
            net = np.net
            print 'NET INFO:',net.name,net.id,net.virtual_address,net.port,net.username
    
    def on_peer_get_info(self, widget):
        n = self._netbook.get_current_page()
        np = self._get_np(self._netbook.get_nth_page(n))
        model, iter = np.selection.get_selected()

        if iter is not None:
            peer = model.get_value(iter, 3)
            print 'PEER INFO:',peer.name,peer.id,peer.vip_str
        
        
    def on_network_connect_peer(self, widget):
        n = self._netbook.get_current_page()
        np = self._get_np(self._netbook.get_nth_page(n))
        if np is not None:
            net = np.net
            
            # get address
            def get_address(dialog, responseid, entry):
                if responseid == gtk.RESPONSE_OK:
                    txt = entry.get_text()
                    addr, port = txt.split(':')
                    addr = (addr, int(port))
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
            dialog.format_secondary_markup('Accepts input of the form: &lt;address&gt;:&lt;port&gt;')
            hbox = gtk.HBox(False, 0)
            hbox.pack_start(gtk.Label('Address: '), False, 5, 5)
            entry = gtk.Entry()
            entry.connect('activate', lambda *x: dialog.response(gtk.RESPONSE_OK))
            hbox.pack_end(entry)
            dialog.vbox.pack_end(hbox, True, True, 0)
            dialog.show_all()
            dialog.connect('response', get_address, entry)
            
        
    def on_peer_copy_ip(self, widget):
        n = self._netbook.get_current_page()
        np = self._get_np(self._netbook.get_nth_page(n))
        model, iter = np.selection.get_selected()

        if iter is not None:
            peer = model.get_value(iter, 3)
            clip = gtk.clipboard_get()
            clip.set_text(peer.vip_str)

    def on_peerlist_click(self, widget, event, np):
        if event.button == 3:
            x, y = int(event.x), int(event.y)
            path_info = widget.get_path_at_pos(x, y)
            if path_info is not None:
                path, col, cx, cy = path_info
                widget.grab_focus()
                widget.set_cursor(path, col, 0)
                
                self._peer_menu.popup(None, None, None, event.button, event.time)

    def on_notebook_click(self, widget, event, np):
        if event.button == 3:
            n = self._netbook.page_num(np.widget)
            self._netbook.set_current_page(n)
            self._network_menu.popup(None, None, None, event.button, event.time)
        

    def on_network_toggle_online(self, widget):
        n = self._netbook.get_current_page()
        np = self._get_np(self._netbook.get_nth_page(n))
        if np is not None:
            net = np.net
            if net.is_running:
                net.stop()

                logger.info('stopping network {0}'.format(net.name))
            else:
                net.start()

                logger.info('starting network {0}'.format(net.name))
        
    def on_network_toggle_enabled(self, widget):
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

    def _add_network(self, nw):
        if nw.id not in self._net_page:
        
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
            

    def _add_peer(self, net, peer):
        self._net_page[net.id].add_peer(peer)
    
    
    def _remove_peer(self, net, peer):
        self._net_page[net.id].remove_peer(peer)
    
    def _network_on(self, net):
        self._add_network(net)
        self._net_page[net.id].update_label()
        
        logger.info('network {0} online'.format(net.name))

    
    def _network_off(self, net):
        self._net_page[net.id].clear()
        self._net_page[net.id].update_label()

        logger.info('network {0} offline'.format(net.name))

    def _network_enabled(self, net):
        self._net_page[net.id].update_label()

        logger.info('network {0} online'.format(net.name))
    
    def _network_disabled(self, net):
        self._net_page[net.id].clear()
        self._net_page[net.id].update_label()

        logger.info('network {0} disabled'.format(net.name))
    
    def _message(self, net, peer, msg):
        print 'msg',net, peer, msg
    



if __name__ == '__main__':
    iface = Interface()
    if len(iface.get_network_dict()) < 1:
        iface.create_new_network('newnetwork')

    mw = MainWin(iface)
    iface.start_all_networks()

    # give it time to bring up teh interface, then open tcp port

    reactor.run()
