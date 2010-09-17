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
import uuid
from gtk import glade
from twisted.internet import reactor, defer
from twisted.python import failure, log, util
from twisted.spread import pb
from twisted.cred.credentials import UsernamePassword
from twisted.internet import error as netError

import util
from interface import Interface
from chatter import ChatterBox

class MainWin:
    def __init__(self, iface):

        self.builder = gtk.Builder()
        self.builder.add_from_file('main.ui')


        self.get_objects()

        self.builder.connect_signals(self)
        self._selection = self._peer_treeview.get_selection()
        
        self._main_window.resize(200,400)
        self._main_window.connect('delete-event', lambda *x: reactor.stop())
        self._main_window.show_all()
        
        nw = iface.get_network_list()[0]
        self._name_label.set_text('%s - %s' % (nw.username, nw.virtual_ip))
        
        #Events
        iface.peer_added += self._add_peer
        iface.peer_removed += self._remove_peer
        iface.network_started += self._network_on
        iface.network_stopped += self._network_off
        iface.message_received += self._message
        
        nws = iface.get_network_list()
        for nw in nws:
            self._peer_model.append(None, [nw, nw.name, ''])
        
        self.iface = iface

    def get_objects(self):
        objects = ('main_window','name_label','peer_treeview','peer_model','peer_menu','network_menu')
        go = self.builder.get_object
        for obj_name in objects:
            setattr(self, "_" + obj_name, go(obj_name))

    def on_network_get_info(self, widget):
        model, iter = self._selection.get_selected()

        if iter is not None:
            net = model.get_value(iter, 0)
            print 'NET INFO:',net.name,net.id,net.virtual_address,net.port,net.username
            
    
    def on_peer_get_info(self, widget):
        model, iter = self._selection.get_selected()

        if iter is not None:
            peer = model.get_value(iter, 0)
        
    def on_network_connect_peer(self, widget):
        model, iter = self._selection.get_selected()
        if iter is not None:
            net = model.get_value(iter, 0)
            
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
        model, iter = self._selection.get_selected()

        if iter is not None:
            peer = model.get_value(iter, 0)
            clip = gtk.clipboard_get()
            clip.set_text(util.decode_ip(peer.vip))
            print 'clip'
        
    def on_peer_treeview_button_press_event(self, widget, event):
        if event.button == 3:
            x, y = int(event.x), int(event.y)
            path_info = widget.get_path_at_pos(x, y)
            if path_info is not None:
                path, col, cx, cy = path_info
                widget.grab_focus()
                widget.set_cursor(path, col, 0)
                
                # check if network or peer
                if len(path) == 1:
                    self._network_menu.popup(None, None, None, event.button, event.time)
                else:
                    self._peer_menu.popup(None, None, None, event.button, event.time)

    def _add_peer(self, net, peer):
        iter = self._find_iter(net)
        #print iter
        if iter is not None:
            print 'add',peer.name
            self._peer_model.append(iter, [peer, '%s - %s'%(peer.name,util.decode_ip(peer.vip)), peer.vip])
    
    def _find_iter(self, obj):
        iter = self._peer_model.iter_children(None)
        def next_iter(iter):
            while iter:
                yield iter
                iter = self._peer_model.iter_children(iter) or self._peer_model.iter_next(iter)

        for it in next_iter(iter):
#            print 'count',it,self._treestore1.get_value(it,0)
            if self._peer_model.get_value(it, 0) is obj:
                return it        
            
        return None
            
    
    def _remove_peer(self, net, peer):
        iter = self._find_iter(peer)
        if iter is not None:
            self._peer_model.remove(iter)
    
        print 'rem',peer.name
    
    def _network_on(self, net):
        iter = self._find_iter(net)
        #print iter
        if iter is None:
            self._peer_model.append(None, [net, net.name, ''])

        print 'on',net.name
    
    def _network_off(self, net):
        print 'off',net
    
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
